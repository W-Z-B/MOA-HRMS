from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[]), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[]), name="docs"),
    # Release 1
    path("api/v1/auth/", include("iam.urls")),
    path("api/v1/org/", include("org.urls")),
    path("api/v1/", include("people.urls")),
    path("api/v1/leave/", include("leave.urls")),
    path("api/v1/reports/", include("reports.api")),
    path("api/v1/notifications/", include("notifications.api")),
    # Release 2 scaffolds (read-only until their sprints)
    path("api/v1/attendance/", include("attendance.api")),
    path("api/v1/performance/", include("performance.api")),
    path("api/v1/training/", include("training.api")),
    path("api/v1/payroll/", include("payroll.api")),
]

# Personnel documents are never served from MEDIA_URL; use the audited /documents/{id}/download/ endpoint.
