from django.urls import path
from rest_framework.routers import SimpleRouter

from privacy import restriction_views, retention_views, views

router = SimpleRouter()
router.register("notices", views.NoticeViewSet, basename="privacy-notice")
router.register("corrections", views.CorrectionViewSet, basename="correction")
router.register("retention-rules", retention_views.RuleViewSet, basename="retention-rule")
router.register("disposal-runs", retention_views.RunViewSet, basename="disposal-run")
router.register("breaches", retention_views.BreachViewSet, basename="breach")
router.register("restrictions", restriction_views.RestrictionViewSet, basename="restriction")
router.register("objections", restriction_views.ObjectionViewSet, basename="objection")

urlpatterns = [
    path("notice/", views.current_notice_view, name="privacy-notice-current"),
    path("notice/acknowledge/", views.acknowledge_view, name="privacy-notice-acknowledge"),
    path("my-record/", views.own_record_view, name="privacy-own-record"),
    path("employees/<int:pk>/record/", views.employee_record_view, name="privacy-employee-record"),
    *router.urls,
]
