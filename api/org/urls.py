from rest_framework.routers import DefaultRouter

from org import views

router = DefaultRouter()
router.register("campuses", views.CampusViewSet)
router.register("units", views.OrgUnitViewSet)
router.register("salary-scales", views.SalaryScaleViewSet)
router.register("grades", views.GradeViewSet)
router.register("positions", views.PositionViewSet)

urlpatterns = router.urls
