# (c) 2015 ACSONE SA/NV, Dhinesh D

# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.tests import common


class TestIrConfigParameter(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.db = cls.env.cr.dbname
        cls.param_obj = cls.env["ir.config_parameter"]
        cls.data_obj = cls.env["ir.model.data"]
        cls.delay = cls.env.ref("auth_session_timeout.inactive_session_time_out_delay")

    def test_check_session_param_delay(self):
        delay = self.param_obj._auth_timeout_get_parameter_delay()
        self.assertEqual(delay, int(self.delay.value))
        self.assertIsInstance(delay, int)

    def test_check_session_param_urls(self):
        urls = self.param_obj._auth_timeout_get_parameter_ignored_urls()
        self.assertIsInstance(urls, list)


class TestIrConfigParameterCaching(common.TransactionCase):
    def test_delay_changes_are_effective(self):
        params = self.env["ir.config_parameter"].sudo()
        self.assertEqual(params._auth_timeout_get_parameter_delay(), 7200)
        params.set_int("inactive_session_time_out_delay", 7201)
        self.assertEqual(params._auth_timeout_get_parameter_delay(), 7201)

    def test_ignored_urls_changes_are_effective(self):
        params = self.env["ir.config_parameter"].sudo()
        params._auth_timeout_get_parameter_ignored_urls()
        params.set_str("inactive_session_time_out_ignored_url", "/example")
        self.assertEqual(
            params._auth_timeout_get_parameter_ignored_urls(), ["/example"]
        )

    def test_deleted_delay_uses_default_and_can_be_recreated(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_int("inactive_session_time_out_delay", 10)
        self.assertEqual(params._auth_timeout_get_parameter_delay(), 10)
        self.env.ref("auth_session_timeout.inactive_session_time_out_delay").unlink()
        self.assertEqual(params._auth_timeout_get_parameter_delay(), 7200)
        params.set_int("inactive_session_time_out_delay", 20)
        self.assertEqual(params._auth_timeout_get_parameter_delay(), 20)
