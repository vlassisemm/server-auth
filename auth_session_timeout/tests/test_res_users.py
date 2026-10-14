# Copyright 2016-2017 LasLabs Inc.
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from contextlib import contextmanager
from unittest import mock

from odoo.http.session import (
    SessionExpiredException,
    get_default_session,
    session_store,
)
from odoo.tests.common import TransactionCase
from odoo.tools.misc import mute_logger


class TestResUsers(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.ResUsers = cls.env["res.users"]

    @contextmanager
    def _mock_assets(self, assets=None):
        """It provides mocked imports from res_users.py
        :param assets: (list) Name of imports to mock. Mocks `http` if None
        :return: (dict) Dictionary of mocks, keyed by module name
        """
        if assets is None:
            assets = ["http"]
        patches = {name: mock.DEFAULT for name in assets}
        with mock.patch.multiple(
            "odoo.addons.auth_session_timeout.models.res_users", **patches
        ) as mocks:
            yield mocks

    def test_session_validity_no_request(self):
        """It should return immediately if no request"""
        with self._mock_assets() as assets:
            assets["http"].request = False
            res = self.ResUsers._auth_timeout_check()
            self.assertFalse(res)

    def test_session_termination_clears_authentication(self):
        session = session_store().new()
        session.update(get_default_session(), db=self.env.cr.dbname, uid=self.env.uid)
        self.assertTrue(self.ResUsers._auth_timeout_session_terminate(session))
        self.assertFalse(session.uid)
        self.assertEqual(session.db, self.env.cr.dbname)
        self.assertTrue(session.should_rotate)

    @mute_logger("odoo.addons.auth_session_timeout.models.res_users")
    def test_unreadable_session_is_rejected(self):
        with self._mock_assets(
            ["http", "getmtime", "logout", "session_store"]
        ) as assets:
            assets["getmtime"].side_effect = OSError
            with self.assertRaises(SessionExpiredException):
                self.ResUsers._auth_timeout_check()

    def test_session_termination_can_be_cancelled(self):
        with self._mock_assets(
            ["http", "getmtime", "utime", "session_store"]
        ) as assets:
            assets["getmtime"].return_value = 0
            with mock.patch.object(
                type(self.ResUsers),
                "_auth_timeout_session_terminate",
                return_value=False,
            ):
                self.assertFalse(self.ResUsers._auth_timeout_check())
            assets["utime"].assert_called_once()
