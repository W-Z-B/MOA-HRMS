from django.urls import path

from iam import views

urlpatterns = [
    path("login/", views.login_view, name="auth-login"),
    path("logout/", views.logout_view, name="auth-logout"),
    path("me/", views.me_view, name="auth-me"),
    path("mfa/enrol/", views.mfa_enrol, name="auth-mfa-enrol"),
    path("mfa/verify/", views.mfa_verify, name="auth-mfa-verify"),
    path("sessions/", views.sessions_view, name="auth-sessions"),
    path("sessions/end-others/", views.end_other_sessions_view, name="auth-sessions-end-others"),
    path("sessions/<int:pk>/", views.end_session_view, name="auth-session-end"),
    path("password/forgot/", views.forgot_password_view, name="auth-password-forgot"),
    path("password/check/", views.check_link_view, name="auth-password-check"),
    path("password/set/", views.set_password_view, name="auth-password-set"),
    path("password/change/", views.change_password_view, name="auth-password-change"),
]
