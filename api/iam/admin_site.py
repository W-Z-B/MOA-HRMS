"""The Django admin, held to the same sign-in rules as the web app.

The stock admin has its own password form, which skips the failed-login lockout and the authenticator
step. Here the admin has no form of its own: people sign in through the web app (lockout, then TOTP for
privileged roles) and the admin accepts that session only once it is verified.
"""

from django.contrib import admin
from django.http import HttpResponseRedirect

from iam.permissions import MFA_SESSION_KEY
from iam.services import requires_mfa


class HrmsAdminSite(admin.AdminSite):
    site_header = "GSA HRMS administration"
    site_title = "GSA HRMS administration"
    index_title = "Records"

    def has_permission(self, request) -> bool:
        if not super().has_permission(request):
            return False
        return not requires_mfa(request.user) or bool(request.session.get(MFA_SESSION_KEY, False))

    def login(self, request, extra_context=None):
        """No password form of its own: people sign in through the web app, then open the admin."""
        return HttpResponseRedirect("/")
