from django.urls import path

from . import views

urlpatterns = [
    path("projects/<int:project_id>/plan/", views.PlanProcessView.as_view(), name="plan-process"),
    path("projects/<int:project_id>/plan/step/", views.PlanStepView.as_view(), name="plan-step"),
    path(
        "projects/<int:project_id>/plan/content/",
        views.PlanContentView.as_view(),
        name="plan-content",
    ),
    path("projects/<int:project_id>/plan/paper/", views.PlanPaperView.as_view(), name="plan-paper"),
    path(
        "projects/<int:project_id>/plan/consultations/",
        views.ConsultationsView.as_view(),
        name="plan-consultations",
    ),
    path(
        "projects/<int:project_id>/plan/comments/",
        views.PlanCommentsView.as_view(),
        name="plan-comments",
    ),
    path(
        "plan-consultations/<int:consultation_id>/display/",
        views.ConsultationDisplayView.as_view(),
        name="plan-consultation-display",
    ),
    path(
        "plan-consultations/<int:consultation_id>/minutes/",
        views.ConsultationMinutesView.as_view(),
        name="plan-consultation-minutes",
    ),
    path(
        "plan-comments/<int:comment_id>/reply/",
        views.PlanCommentReplyView.as_view(),
        name="plan-comment-reply",
    ),
]
