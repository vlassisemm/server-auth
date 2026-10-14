# License LGPL-3.0 or later (http://www.gnu.org/licenses/lgpl.html).

from odoo import models

from odoo.addons.base.models.ir_module import assert_log_admin_access

from ..models.res_users import _password_demo_loading


class IrDemo(models.TransientModel):
    _inherit = "ir.demo"

    @assert_log_admin_access
    def install_demo(self):
        # This server-controlled scope cannot be supplied in RPC context.
        token = _password_demo_loading.set(True)
        try:
            return super().install_demo()
        finally:
            _password_demo_loading.reset(token)
