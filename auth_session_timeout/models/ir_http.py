# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
from os.path import getmtime

from odoo import models
from odoo.http import request
from odoo.http.session import session_store


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _authenticate(cls, endpoint):
        if (
            request
            and request.session.uid
            and "_auth_timeout_last_activity" not in request.session
        ):
            # Core device tracing can save the session during authentication.
            # Capture the legacy clock before that save changes its file time.
            try:
                request._auth_timeout_last_activity = getmtime(
                    session_store().get_session_path(request.session.sid)
                )
            except OSError:
                request._auth_timeout_last_activity = False
        res = super()._authenticate(endpoint=endpoint)
        if (
            request
            and request.session
            and request.session.uid
            and not request.env["res.users"].browse(request.session.uid)._is_public()
        ):
            request.env.user._auth_timeout_check()
        return res
