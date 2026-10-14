# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user


class TestPasswordHistoryAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.history = cls.env["res.users.pass.history"]
        cls.internal = new_test_user(
            cls.env, "history_internal", password="Str0ng!History"
        )
        cls.portal = new_test_user(
            cls.env,
            "history_portal",
            groups="base.group_portal",
            password="Str0ng!History",
        )
        cls.manager = new_test_user(
            cls.env,
            "history_manager",
            groups="base.group_erp_manager",
            password="Str0ng!History",
        )
        cls.other = new_test_user(cls.env, "history_other", password="Str0ng!History")
        cls.other_company = cls.env["res.company"].create(
            {"name": "History other company"}
        )
        cls.other.company_ids |= cls.other_company
        cls.other.company_id = cls.other_company
        cls.records = cls.history.create(
            [
                {"user_id": user.id, "password_crypt": "private hash"}
                for user in (cls.internal, cls.portal, cls.manager, cls.other)
            ]
        )

    def test_users_only_read_their_own_history(self):
        for user in (self.internal, self.portal, self.manager):
            with self.subTest(user=user.login):
                visible = self.history.with_user(user).search([])
                self.assertTrue(visible)
                self.assertEqual(visible.user_id, user)
                other = self.records.filtered(
                    lambda record: record.user_id == self.other
                )
                with self.assertRaises(AccessError):
                    other.with_user(user).read(["password_crypt"])

    def test_users_cannot_modify_or_remove_history(self):
        for user in (self.internal, self.portal, self.manager):
            record = self.records.filtered(
                lambda record, user=user: record.user_id == user
            )
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                record.with_user(user).write({"password_crypt": "replacement"})
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                record.with_user(user).unlink()

    def test_only_user_manager_can_create_another_users_history(self):
        for user in (self.internal, self.portal):
            with self.subTest(user=user.login), self.assertRaises(AccessError):
                self.history.with_user(user).create({"user_id": self.other.id})
        record = self.history.with_user(self.manager).create({"user_id": self.other.id})
        self.assertEqual(record.sudo().user_id, self.other)

    def test_public_user_cannot_read_history(self):
        with self.assertRaises(AccessError):
            self.history.with_user(self.env.ref("base.public_user")).search([])
