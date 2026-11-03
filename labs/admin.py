from django.contrib import admin

from .models import Job, Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("username", "full_name", "cohort", "status", "node_port", "spring_port", "imported")
    list_filter = ("status", "cohort", "imported")
    search_fields = ("username", "full_name", "email")
    readonly_fields = ("created_at", "updated_at", "provisioned_at")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "username", "status", "created_at", "finished_at")
    list_filter = ("status", "kind")
    search_fields = ("username",)
    readonly_fields = [f.name for f in Job._meta.fields]
