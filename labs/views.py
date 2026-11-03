import csv

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import ComponentsForm, ConfirmRemoveForm, EnrollForm
from .models import ALL_COMPONENTS, Job, Student
from .services import (HelperError, enroll, ensure_portal_user, generate_password, queue_job,
                       service_op, service_status)


@login_required
def home(request):
    if request.user.is_staff:
        return redirect("dashboard")
    return redirect("my_lab")


# ---------------------------------------------------------------------------
# 학생 화면
# ---------------------------------------------------------------------------
@login_required
def my_lab(request):
    student = getattr(request.user, "student", None)
    if student is None:
        if request.user.is_staff:
            return redirect("dashboard")
        raise Http404("No lab environment is assigned to this account.")

    if request.method == "POST":
        svc, op = request.POST.get("service"), request.POST.get("op")
        try:
            out = service_op(student, svc, op)
            messages.success(request, f"{svc} {op}: {out or 'ok'}")
        except HelperError as e:
            messages.error(request, f"{svc} {op} failed: {e}")
        return redirect("my_lab")

    return render(request, "labs/my_lab.html", {
        "s": student, "status": service_status(student),
    })


# ---------------------------------------------------------------------------
# 교수자 화면
# ---------------------------------------------------------------------------
@staff_member_required
def dashboard(request):
    qs = Student.objects.all()
    q = request.GET.get("q", "").strip()
    cohort = request.GET.get("cohort", "")
    status = request.GET.get("status", "")
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(full_name__icontains=q) | Q(email__icontains=q))
    if cohort:
        qs = qs.filter(cohort=cohort)
    if status:
        qs = qs.filter(status=status)
    else:
        qs = qs.exclude(status=Student.Status.REMOVED)
    counts = dict(Student.objects.values_list("status").annotate(n=Count("id")))
    return render(request, "labs/dashboard.html", {
        "students": qs,
        "q": q, "cohort": cohort, "status": status,
        "cohorts": Student.objects.exclude(cohort="").values_list("cohort", flat=True).distinct().order_by("cohort"),
        "statuses": Student.Status.choices,
        "counts": counts,
        "pending_jobs": Job.objects.filter(status__in=[Job.Status.QUEUED, Job.Status.RUNNING]).count(),
    })


@staff_member_required
@require_POST
def bulk_action(request):
    ids = request.POST.getlist("ids")
    action = request.POST.get("action")
    students = Student.objects.filter(pk__in=ids)
    kinds = {"apply": Job.Kind.CREATE, "password": Job.Kind.PASSWORD}
    if action not in kinds or not students:
        messages.error(request, "Select students and an action.")
        return redirect("dashboard")
    for s in students:
        if action == "password":
            _new_password(s)
        queue_job(kinds[action], s, request.user)
    messages.success(request, f"Queued '{action}' for {len(students)} student(s).")
    return redirect("jobs")


@staff_member_required
def enroll_view(request):
    form = EnrollForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            created, skipped = enroll(
                form.cleaned_data["rows"], cohort=form.cleaned_data["cohort"],
                components=form.cleaned_data["components"], created_by=request.user,
            )
        except ValueError as e:
            messages.error(request, str(e))
        else:
            if created:
                messages.success(request, f"{len(created)} student(s) added and queued for provisioning.")
            if skipped:
                messages.warning(request, f"Already registered, skipped: {', '.join(skipped)}")
            return redirect("jobs")
    return render(request, "labs/enroll.html", {"form": form})


def _new_password(student):
    student.initial_password = generate_password(student.username)
    student.save(update_fields=["initial_password"])
    if student.user:
        student.user.set_password(student.initial_password)
        student.user.save(update_fields=["password"])
    else:
        ensure_portal_user(student, student.initial_password)


@staff_member_required
def student_detail(request, username):
    s = get_object_or_404(Student, username=username)
    form = ComponentsForm(request.POST or None, initial={
        "components": s.components, "cohort": s.cohort, "full_name": s.full_name, "email": s.email,
    })
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "service":
            svc, op = request.POST.get("service"), request.POST.get("op")
            try:
                out = service_op(s, svc, op)
                messages.success(request, f"{svc} {op}: {out or 'ok'}")
            except HelperError as e:
                messages.error(request, f"{svc} {op} failed: {e}")
        elif action == "apply" and form.is_valid():
            s.components = [c for c in ALL_COMPONENTS if c in form.cleaned_data["components"]]
            s.cohort = form.cleaned_data["cohort"]
            s.full_name = form.cleaned_data["full_name"]
            s.email = form.cleaned_data["email"]
            s.save()
            queue_job(Job.Kind.CREATE, s, request.user)
            messages.success(request, "Saved; provisioning job queued.")
        elif action == "password":
            _new_password(s)
            queue_job(Job.Kind.PASSWORD, s, request.user)
            messages.success(request, f"New password generated: {s.initial_password} (applying…)")
        elif action == "portal_password":
            ensure_portal_user(s, s.initial_password)
            s.user.set_password(s.initial_password)
            s.user.is_active = True
            s.user.save()
            messages.success(request, "Portal login reset to the initial password.")
        return redirect("student_detail", username=s.username)

    return render(request, "labs/student_detail.html", {
        "s": s, "form": form, "status": service_status(s), "jobs": s.jobs.all()[:20],
    })


@staff_member_required
def student_remove(request, username):
    s = get_object_or_404(Student, username=username)
    form = ConfirmRemoveForm(request.POST or None, username=s.username)
    if request.method == "POST" and form.is_valid():
        kind = Job.Kind.PURGE if form.cleaned_data["purge"] else Job.Kind.REMOVE
        queue_job(kind, s, request.user)
        messages.success(request, f"{kind.label} queued for {s.username}.")
        return redirect("jobs")
    return render(request, "labs/student_remove.html", {"s": s, "form": form})


@staff_member_required
def jobs(request):
    qs = Job.objects.select_related("student", "created_by")[:200]
    active = Job.objects.filter(status__in=[Job.Status.QUEUED, Job.Status.RUNNING]).exists()
    return render(request, "labs/jobs.html", {"jobs": qs, "active": active})


@staff_member_required
def job_detail(request, pk):
    job = get_object_or_404(Job, pk=pk)
    return render(request, "labs/job_detail.html", {"job": job})


def _cell(v):
    """스프레드시트 수식 주입 방지."""
    v = str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


@staff_member_required
def export_csv(request):
    qs = Student.objects.exclude(status=Student.Status.REMOVED)
    cohort = request.GET.get("cohort")
    if cohort:
        qs = qs.filter(cohort=cohort)
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="students{("-" + cohort) if cohort else ""}.csv"'
    resp.write("﻿")  # Excel 에서 UTF-8 로 열리도록
    w = csv.writer(resp)
    w.writerow(["username", "full_name", "email", "cohort", "password", "site", "node_red_port",
                "spring_port", "mqtt_topic", "status"])
    for s in qs:
        w.writerow([_cell(v) for v in (
            s.username, s.full_name, s.email, s.cohort, s.initial_password, s.site_url,
            s.node_port, s.spring_port, s.mqtt_topic, s.status)])
    return resp
