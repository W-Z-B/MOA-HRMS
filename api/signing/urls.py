from rest_framework.routers import SimpleRouter

from signing import views

router = SimpleRouter()
router.register("mine", views.MySignaturesViewSet, basename="my-signature")
router.register("requests", views.SignatureRequestViewSet, basename="signature-request")

urlpatterns = router.urls
