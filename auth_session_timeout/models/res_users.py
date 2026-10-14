# (c) 2015 ACSONE SA/NV, Dhinesh D

# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

import logging
from os import utime
from os.path import getmtime
from time import time

from odoo import api, http, models
from odoo.http.session import SessionExpiredException, logout, session_store

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _auth_timeout_get_ignored_urls(self):
        """Pluggable method for calculating ignored urls
        Defaults to stored config param
        """
        params = self.env["ir.config_parameter"]
        return params._auth_timeout_get_parameter_ignored_urls()

    @api.model
    def _auth_timeout_deadline_calculate(self):
        """Pluggable method for calculating timeout deadline
        Defaults to current time minus delay using delay stored as config
        param.
        """
        params = self.env["ir.config_parameter"]
        delay = params._auth_timeout_get_parameter_delay()
        if delay <= 0:
            return False
        return time() - delay

    @api.model
    def _auth_timeout_session_terminate(self, session):
        """Pluggable method for terminating a timed-out session

        This is a late stage where a session timeout can be aborted.
        Useful if you want to do some heavy checking, as it won't be
        called unless the session inactivity deadline has been reached.

        Return:
            True: session terminated
            False: session timeout cancelled
        """
        if session.db and session.uid:
            logout(session, keep_db=True)
            # JSON-RPC errors skip post_dispatch and its normal session save.
            # Revoke the persisted session before rejecting this request.
            session_store().delete(session)
        return True

    @api.model
    def _auth_timeout_check(self):
        """Perform session timeout validation and expire if needed."""

        if not http.request:
            return

        session = http.request.session

        # Calculate deadline
        deadline = self._auth_timeout_deadline_calculate()

        # Keep activity independent of core session/device metadata saves.
        # Legacy sessions inherit the file time captured before authentication.
        last_activity = session.get("_auth_timeout_last_activity")
        new_activity_clock = last_activity is None
        if last_activity is None:
            last_activity = getattr(http.request, "_auth_timeout_last_activity", None)
            if last_activity is None:
                path = session_store().get_session_path(session.sid)
                try:
                    last_activity = getmtime(path)
                except OSError:
                    _logger.exception("Exception reading session file modified time.")
                    last_activity = False
            if last_activity is not False:
                session["_auth_timeout_last_activity"] = last_activity

        expired = deadline is not False and (
            last_activity is False or last_activity < deadline
        )

        # Try to terminate the session
        terminated = False
        if expired:
            terminated = self._auth_timeout_session_terminate(session)

        # If session terminated, all done
        if terminated:
            raise SessionExpiredException("Session expired")

        # Else, conditionally update session modified and access times
        ignored_urls = self._auth_timeout_get_ignored_urls()

        active_request = http.request.httprequest.path not in ignored_urls
        if active_request:
            session["_auth_timeout_last_activity"] = time()
            if "path" not in locals():
                path = session_store().get_session_path(
                    session.sid,
                )
            try:
                utime(path, None)
            except OSError:
                _logger.exception(
                    "Exception updating session file access/modified times.",
                )

        if active_request or new_activity_clock:
            # Error responses skip the normal session save after dispatch.
            # Persist trusted activity now, including a legacy ignored clock.
            session_store().save(session)
