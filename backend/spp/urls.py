from django.urls import path

from . import views

urlpatterns = [
    path("projects/<int:project_id>/spp/", views.SaveView.as_view(), name="project-spp-save"),
    path("spp/open/", views.OpenView.as_view(), name="spp-open"),
    path("spp/keys/", views.KeysView.as_view(), name="spp-keys"),
]
