from rest_framework.routers import SimpleRouter

from letters import views

router = SimpleRouter()  # no root page: the register itself lives at the empty path
router.register("templates", views.LetterTemplateViewSet)
router.register("mine", views.MyLettersViewSet, basename="my-letter")
router.register("", views.LetterViewSet, basename="letter")

urlpatterns = router.urls
