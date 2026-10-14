# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from io import BytesIO
from unittest.mock import patch

from odoo import tools
from odoo.exceptions import UserError
from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tools.convert import convert_xml_import
from odoo.tools.misc import mute_logger


@tagged("post_install", "-at_install")
class TestPasswordPolicyContext(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.password = "Secure!Initial12"
        cls.user = new_test_user(cls.env, "policy_context_user", password=cls.password)

    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_int(
            "auth_password_policy.minlength", 12
        )

    def _change_password_rpc(self, old_password, new_password):
        self.authenticate(self.user.login, old_password)
        payload = self.build_rpc_payload(
            {
                "model": "res.users",
                "method": "change_password",
                "args": [old_password, new_password],
                "kwargs": {
                    "context": {
                        "install_mode": True,
                        "install_demo": True,
                        "install_module": "base",
                        "install_filename": "res_users.xml",
                    }
                },
            }
        )
        # Exercise production policy rather than the test-isolation exemption.
        with patch.dict(tools.config._runtime_options, {"test_enable": False}):
            return self.url_open(
                "/web/dataset/call_kw/res.users/change_password", json=payload
            ).json()

    @mute_logger("odoo.http")
    def test_rpc_install_context_cannot_bypass_minimum_length(self):
        response = self._change_password_rpc(self.password, "weak")
        self.assertIn("error", response)
        self.assertEqual(response["error"]["data"]["name"], "odoo.exceptions.UserError")

    @mute_logger("odoo.http")
    def test_rpc_install_context_cannot_bypass_password_history(self):
        current_password = "Secure!Current12"
        self.user.password = current_password
        response = self._change_password_rpc(current_password, self.password)
        self.assertIn("error", response)
        self.assertIn(
            "Cannot use the most recent", response["error"]["data"]["message"]
        )

    def test_ready_registry_sudo_context_cannot_bypass_policy(self):
        user = (
            self.user.with_user(self.user)
            .sudo()
            .with_context(install_mode=True, install_demo=True)
        )
        with (
            patch.dict(tools.config._runtime_options, {"test_enable": False}),
            self.assertRaises(UserError),
        ):
            user._check_password_policy(["weak"])

    def test_admin_demo_loader_keeps_a_scoped_policy_exemption(self):
        def load_demo(env):
            xml = BytesIO(b"""<odoo>
                <record id="context_demo_user" model="res.users">
                    <field name="name">Context demo user</field>
                    <field name="login">context_demo_user</field>
                    <field name="password">weak</field>
                </record>
            </odoo>""")
            xml.name = "context_demo.xml"
            convert_xml_import(
                env(su=True, context=dict(env.context, install_demo=True)),
                "password_security",
                xml,
                {},
                "init",
            )

        self.authenticate("admin", "admin")
        payload = self.build_rpc_payload(
            {"model": "ir.demo", "method": "install_demo", "args": [[]], "kwargs": {}}
        )
        with (
            patch.dict(tools.config._runtime_options, {"test_enable": False}),
            patch("odoo.modules.loading.force_demo", side_effect=load_demo),
        ):
            response = self.url_open(
                "/web/dataset/call_kw/ir.demo/install_demo", json=payload
            ).json()
        self.assertIn("result", response)
        self.assertTrue(self.env.ref("password_security.context_demo_user").exists())
        user = (
            self.user.with_user(self.user)
            .sudo()
            .with_context(install_mode=True, install_demo=True)
        )
        with (
            patch.dict(tools.config._runtime_options, {"test_enable": False}),
            self.assertRaises(UserError),
        ):
            user._check_password_policy(["weak"])

    @mute_logger("odoo.http", "odoo.addons.base.models.ir_module")
    def test_non_admin_cannot_enter_demo_loader_scope(self):
        self.authenticate(self.user.login, self.password)
        payload = self.build_rpc_payload(
            {
                "model": "ir.demo",
                "method": "install_demo",
                "args": [[]],
                "kwargs": {"context": {"install_mode": True, "install_demo": True}},
            }
        )
        with patch.dict(tools.config._runtime_options, {"test_enable": False}):
            response = self.url_open(
                "/web/dataset/call_kw/ir.demo/install_demo", json=payload
            ).json()
        self.assertIn("error", response)

    def test_demo_loader_scope_is_reset_after_failure(self):
        with (
            patch("odoo.modules.loading.force_demo", side_effect=RuntimeError("demo")),
            self.assertRaises(RuntimeError),
        ):
            self.env["ir.demo"].install_demo()
        user = (
            self.user.with_user(self.user)
            .sudo()
            .with_context(install_mode=True, install_demo=True)
        )
        with (
            patch.dict(tools.config._runtime_options, {"test_enable": False}),
            self.assertRaises(UserError),
        ):
            user._check_password_policy(["weak"])
