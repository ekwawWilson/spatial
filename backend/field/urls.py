from django.urls import path

from . import views

urlpatterns = [
    path(
        "projects/<int:project_id>/field-package/",
        views.FieldPackageView.as_view(),
        name="project-field-package",
    ),
    path(
        "projects/<int:project_id>/field-package/basemap/",
        views.FieldBasemapView.as_view(),
        name="project-field-basemap",
    ),
]
