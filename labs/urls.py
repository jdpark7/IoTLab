from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("my/", views.my_lab, name="my_lab"),
    path("staff/", views.dashboard, name="dashboard"),
    path("staff/bulk/", views.bulk_action, name="bulk_action"),
    path("staff/enroll/", views.enroll_view, name="enroll"),
    path("staff/export.csv", views.export_csv, name="export_csv"),
    path("staff/jobs/", views.jobs, name="jobs"),
    path("staff/jobs/<int:pk>/", views.job_detail, name="job_detail"),
    path("staff/students/<str:username>/", views.student_detail, name="student_detail"),
    path("staff/students/<str:username>/remove/", views.student_remove, name="student_remove"),
]
