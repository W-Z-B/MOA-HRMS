from django.urls import path
from rest_framework.routers import SimpleRouter

from privacy import views

router = SimpleRouter()
router.register("notices", views.NoticeViewSet, basename="privacy-notice")
router.register("corrections", views.CorrectionViewSet, basename="correction")

urlpatterns = [
    path("notice/", views.current_notice_view, name="privacy-notice-current"),
    path("notice/acknowledge/", views.acknowledge_view, name="privacy-notice-acknowledge"),
    path("my-record/", views.own_record_view, name="privacy-own-record"),
    path("employees/<int:pk>/record/", views.employee_record_view, name="privacy-employee-record"),
    *router.urls,
]
