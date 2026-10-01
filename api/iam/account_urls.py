from rest_framework.routers import SimpleRouter

from iam import account_views

router = SimpleRouter()
router.register("accounts", account_views.AccountViewSet, basename="account")
router.register("access-reviews", account_views.AccessReviewViewSet, basename="access-review")

urlpatterns = router.urls
