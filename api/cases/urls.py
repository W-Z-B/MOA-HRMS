from rest_framework.routers import SimpleRouter

from cases import views

router = SimpleRouter()
router.register("", views.CaseViewSet, basename="case")

urlpatterns = router.urls
