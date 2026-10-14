# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import os
import time

from odoo import http
from odoo.http import request
from odoo.http.session import session_store
from odoo.tests import HttpCase, tagged


class TimeoutTestController(http.Controller):
    @http.route("/auth_session_timeout/test/session", type="jsonrpc", auth="user")
    def session_info(self):
        return {"uid": request.env.uid}

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
        os.utime(path, (old_time, old_time))
        self.assertEqual(self._session_info()["result"]["uid"], self.session.uid)
        self.assertEqual(os.path.getmtime(path), old_time)
