from django.urls import path
from rest_framework.routers import SimpleRouter

from approvals import views

router = SimpleRouter()
router.register("delegations", views.DelegationViewSet, basename="delegation")

urlpatterns = [path("waiting/", views.waiting, name="approvals-waiting"), *router.urls]
