from django.urls import path

from . import views

urlpatterns = [
    path("work/", views.WorkView.as_view(), name="work"),
    path("work/officers/", views.OfficersView.as_view(), name="work-officers"),
    path("work/assign/", views.AssignView.as_view(), name="work-assign"),
    path("search/", views.SearchView.as_view(), name="search"),
]
