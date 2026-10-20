from django.urls import path

from . import views

urlpatterns = [
    path("reports/compliance/", views.ComplianceView.as_view(), name="reports-compliance"),
    path(
        "reports/compliance/pdf/", views.CompliancePdfView.as_view(), name="reports-compliance-pdf"
    ),
    path("reports/returns/", views.ReturnView.as_view(), name="reports-return"),
]
