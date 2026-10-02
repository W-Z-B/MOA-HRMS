from django.urls import path
from rest_framework.routers import SimpleRouter

from letters import views

router = SimpleRouter()  # no root page: the register itself lives at the empty path
router.register("templates", views.LetterTemplateViewSet)
router.register("mine", views.MyLettersViewSet, basename="my-letter")
router.register("", views.LetterViewSet, basename="letter")

# Checking a letter is open to anyone (item 1.47), so it comes before the register's own paths.
urlpatterns = [path("check/", views.check_letter, name="letter-check"), *router.urls]
