from django.urls import path
from preview import views

urlpatterns = [
    path("", views.index, name="index"),
]
