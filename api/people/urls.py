from rest_framework.routers import DefaultRouter

from people import views

router = DefaultRouter()
router.register("employees", views.EmployeeViewSet, basename="employee")
router.register("assignments", views.AssignmentViewSet, basename="assignment")
router.register("contracts", views.ContractViewSet, basename="contract")
router.register("documents", views.DocumentViewSet, basename="document")

urlpatterns = router.urls
