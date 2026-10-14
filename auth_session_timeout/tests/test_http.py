# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import os
import time
from unittest.mock import patch

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.http.session import session_store
from odoo.tests import HttpCase, tagged
from odoo.tools.misc import mute_logger


class TimeoutTestController(http.Controller):
    @http.route("/auth_session_timeout/test/session", type="jsonrpc", auth="user")
    def session_info(self):
        return {"uid": request.env.uid}

    @http.route("/auth_session_timeout/test/error", type="jsonrpc", auth="user")
    def error(self):
        raise UserError(request.env._("Expected timeout activity test error"))

    @http.route("/auth_session_timeout/test/public", type="jsonrpc", auth="public")
    def public_info(self):
        return {"uid": request.env.uid}


@tagged("post_install", "-at_install")
class TestSessionTimeoutHttp(HttpCase):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_str(
            "inactive_session_time_out_delay", "60"
        )

    def _session_info(self):
        return self.url_open(
            "/auth_session_timeout/test/session", json=self.build_rpc_payload()
        ).json()

    def _age_session(self):
        path = session_store().get_session_path(self.session.sid)
        old_time = time.time() - 120
        session = session_store().get(self.session.sid)
        session["_auth_timeout_last_activity"] = old_time
        session_store().save(session)
        os.utime(path, (old_time, old_time))
        return path

    def test_active_authenticated_session_is_accepted(self):
        self.authenticate("admin", "admin")
        self.assertEqual(self._session_info()["result"]["uid"], self.session.uid)

    def test_active_request_refreshes_idle_deadline(self):
        self.authenticate("admin", "admin")
        self._session_info()
        path = session_store().get_session_path(self.session.sid)
        old_time = time.time() - 30
        session = session_store().get(self.session.sid)
        session["_auth_timeout_last_activity"] = old_time
        session_store().save(session)
        os.utime(path, (old_time, old_time))
        self.assertEqual(self._session_info()["result"]["uid"], self.session.uid)
        self.assertGreater(os.path.getmtime(path), old_time)

    def test_public_session_is_not_timed_out(self):
        self.authenticate(None, None)
        public = self.env.ref("base.public_user")
        self.update_session(
            uid=public.id,
            session_token=public._compute_session_token(self.session.sid),
        )
        self._age_session()
        response = self.url_open(
            "/auth_session_timeout/test/public", json=self.build_rpc_payload()
        ).json()
        self.assertEqual(response["result"]["uid"], public.id)

    def test_idle_authenticated_session_is_rejected(self):
        self.authenticate("admin", "admin")
        sid = self.session.sid
        self._age_session()
        response = self._session_info()
        self.assertEqual(
            response["error"]["data"]["name"],
            "odoo.http.session.SessionExpiredException",
        )
        self.assertFalse(session_store().get(sid).uid)
        self.assertIn("error", self._session_info())

    def test_anonymous_public_endpoint_is_accessible(self):
        self.authenticate(None, None)
        response = self.url_open(
            "/auth_session_timeout/test/public", json=self.build_rpc_payload()
        ).json()
        self.assertEqual(response["result"]["uid"], self.env.ref("base.public_user").id)
        self.assertIn("error", self._session_info())

    def test_idle_authenticated_public_endpoint_is_rejected(self):
        self.authenticate("admin", "admin")
        self._age_session()
        response = self.url_open(
            "/auth_session_timeout/test/public", json=self.build_rpc_payload()
        ).json()
        self.assertIn("error", response)

    def test_disabled_timeout_keeps_idle_session(self):
        self.env["ir.config_parameter"].sudo().set_str(
            "inactive_session_time_out_delay", "0"
        )
        self.authenticate("admin", "admin")
        self._age_session()
        self.assertEqual(self._session_info()["result"]["uid"], self.session.uid)

    def test_ignored_endpoint_does_not_extend_idle_deadline(self):
        self.env["ir.config_parameter"].sudo().set_str(
            "inactive_session_time_out_ignored_url",
            "/auth_session_timeout/test/session",
        )
        self.authenticate("admin", "admin")
        self._session_info()  # Initialize the core device metadata before aging.
        path = session_store().get_session_path(self.session.sid)
        old_time = time.time() - 30
        session = session_store().get(self.session.sid)
        session["_auth_timeout_last_activity"] = old_time
        session_store().save(session)
        os.utime(path, (old_time, old_time))
        self.assertEqual(self._session_info()["result"]["uid"], self.session.uid)
        self.assertEqual(os.path.getmtime(path), old_time)
        self.assertEqual(
            session_store().get(self.session.sid)["_auth_timeout_last_activity"],
            old_time,
        )

    def _tracked_idle_session(self, age, legacy=False):
        self.env["ir.config_parameter"].sudo().set_int(
            "inactive_session_time_out_delay", 7200
        )
        self.authenticate("admin", "admin", session_extra={"_trace_disable": False})
        self._session_info()
        session = session_store().get(self.session.sid)
        last_activity = time.time() - age
        for device in session["_devices"].values():
            device["last_activity"] = int(last_activity)
        if legacy:
            session.pop("_auth_timeout_last_activity", None)
        else:
            session["_auth_timeout_last_activity"] = last_activity
        session_store().save(session)
        path = session_store().get_session_path(session.sid)
        os.utime(path, (last_activity, last_activity))
        return last_activity, path

    def test_tracked_long_idle_session_is_rejected(self):
        self._tracked_idle_session(10800)
        response = self._session_info()
        self.assertIn("error", response)

    def test_legacy_long_idle_session_is_rejected_before_core_save(self):
        self._tracked_idle_session(10800, legacy=True)
        response = self._session_info()
        self.assertIn("error", response)

    def test_ignored_core_device_save_keeps_legacy_idle_deadline(self):
        last_activity, path = self._tracked_idle_session(4000, legacy=True)
        self.env["ir.config_parameter"].sudo().set_str(
            "inactive_session_time_out_ignored_url",
            "/auth_session_timeout/test/session",
        )
        self.assertIn("result", self._session_info())
        # Device tracing performs a real pre-authentication file save.
        self.assertGreater(os.path.getmtime(path), last_activity)
        persisted = session_store().get(self.session.sid)
        self.assertEqual(persisted.get("_auth_timeout_last_activity"), last_activity)
        # Another ignored request must still expire on the original deadline.
        with patch(
            "odoo.addons.auth_session_timeout.models.res_users.time",
            return_value=last_activity + 7201,
        ):
            self.assertIn("error", self._session_info())

    def test_tracked_active_request_refreshes_private_activity(self):
        last_activity, _path = self._tracked_idle_session(4000)
        self.assertIn("result", self._session_info())
        persisted = session_store().get(self.session.sid)
        self.assertGreater(
            persisted.get("_auth_timeout_last_activity", 0), last_activity
        )
        with patch(
            "odoo.addons.auth_session_timeout.models.res_users.time",
            return_value=last_activity + 7201,
        ):
            self.assertIn("result", self._session_info())

    @mute_logger("odoo.http")
    def test_authenticated_activity_is_saved_when_controller_raises(self):
        last_activity, _path = self._tracked_idle_session(4000)
        response = self.url_open(
            "/auth_session_timeout/test/error", json=self.build_rpc_payload()
        ).json()
        self.assertIn("error", response)
        persisted = session_store().get(self.session.sid)
        self.assertGreater(persisted["_auth_timeout_last_activity"], last_activity)

    def test_invalid_session_cannot_be_revived_by_activity_tracking(self):
        self.authenticate("admin", "admin")
        self._session_info()
        self.update_session(session_token="invalid")
        response = self.url_open(
            "/auth_session_timeout/test/public", json=self.build_rpc_payload()
        ).json()
        self.assertEqual(response["result"]["uid"], self.env.ref("base.public_user").id)
        self.assertIn("error", self._session_info())
