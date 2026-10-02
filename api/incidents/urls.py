from rest_framework.routers import SimpleRouter

from incidents import views

router = SimpleRouter()
router.register("actions", views.ActionViewSet, basename="incident-action")
router.register("", views.IncidentViewSet, basename="incident")

urlpatterns = router.urls
