from rest_framework.routers import DefaultRouter

from people import career_views, views

router = DefaultRouter()
router.register("employees", views.EmployeeViewSet, basename="employee")
router.register("assignments", views.AssignmentViewSet, basename="assignment")
router.register("contracts", views.ContractViewSet, basename="contract")
router.register("documents", views.DocumentViewSet, basename="document")
router.register("qualifications", views.QualificationViewSet, basename="qualification")
router.register("previous-employment", views.PreviousEmploymentViewSet, basename="previous-employment")
router.register("dependants", views.DependantViewSet, basename="dependant")
router.register("emergency-contacts", views.EmergencyContactViewSet, basename="emergency-contact")
router.register("bank-accounts", views.BankAccountViewSet, basename="bank-account")
router.register("career-events", career_views.CareerEventViewSet, basename="career-event")

urlpatterns = router.urls
