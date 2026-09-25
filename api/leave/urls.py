from rest_framework.routers import DefaultRouter

from leave import views

router = DefaultRouter()
router.register("types", views.LeaveTypeViewSet)
router.register("requests", views.LeaveRequestViewSet, basename="leave-request")
router.register("ledger", views.LeaveLedgerViewSet, basename="leave-ledger")

urlpatterns = router.urls
