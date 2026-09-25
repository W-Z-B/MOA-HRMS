from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from config.views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/schema/", SpectacularAPIView.as_view(permission_classes=[]), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[]), name="docs"),
    # Release 1 module routers are added here as each app lands:
    # path("api/v1/org/", include("org.urls")),
    # path("api/v1/", include("people.urls")),
    # path("api/v1/leave/", include("leave.urls")),
    # path("api/v1/auth/", include("iam.urls")),
]
