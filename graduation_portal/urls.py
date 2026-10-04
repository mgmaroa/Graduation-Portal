from django.urls import path

from . import views

urlpatterns = [
    path("", views.lookup, name="lookup"),
    path("robots.txt", views.robots_txt, name="robots"),
]
