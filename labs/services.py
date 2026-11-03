"""포털 ↔ root 헬퍼(belajarhub-provision) 연결 및 학생 등록 로직."""
import json
import logging
import secrets
import string
import subprocess

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from django.core.exceptions import ValidationError

from .models import ALL_COMPONENTS, SERVICES, Job, Student, username_validator

log = logging.getLogger("labs")

# 헷갈리는 문자(0/O, 1/l/I) 제외
_ALPHABET = "".join(c for c in string.ascii_letters + string.digits if c not in "0O1lI")


class HelperError(Exception):
    pass


def call_helper(payload, timeout=600):
    """헬퍼를 실행하고 JSON 결과를 돌려준다. 비밀번호는 stdin 으로만 전달된다."""
    try:
        proc = subprocess.run(
            settings.LAB_PROVISION_CMD, input=json.dumps(payload), capture_output=True,
            text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        raise HelperError(f"helper could not run: {e}") from e
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise HelperError(
            f"helper returned no JSON (rc={proc.returncode}): {(proc.stderr or proc.stdout).strip()[:500]}"
        )
    return result


# ---------------------------------------------------------------------------
# 비밀번호 / 포트
# ---------------------------------------------------------------------------
def generate_password(username):
    mode = settings.LAB_PASSWORD_MODE
    if mode and mode != "random":
        return mode.format(username=username)
    return "".join(secrets.choice(_ALPHABET) for _ in range(10))


def _free_ports(field, port_range, count):
    used = set(Student.objects.values_list(field, flat=True))
    lo, hi = port_range
    free = [p for p in range(lo, hi + 1) if p not in used]
    if len(free) < count:
        raise ValueError(f"not enough free {field}s in {lo}-{hi}")
    return free[:count]


# ---------------------------------------------------------------------------
# 등록
# ---------------------------------------------------------------------------
def parse_roster(text):
    """한 줄에 'username[,full name[,email]]'. CSV/탭 모두 허용. 헤더/주석은 무시."""
    rows, errors, seen = [], [], set()
    for no, line in enumerate(text.splitlines(), start=1):
        line = line.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        sep = "\t" if "\t" in line else ","
        cols = [c.strip() for c in line.split(sep)]
        username = cols[0]
        if username.lower() == "username":
            continue
        try:
            username_validator(username)
        except ValidationError:
            errors.append(f"line {no}: invalid username {username!r}")
            continue
        if username in seen:
            errors.append(f"line {no}: duplicate {username}")
            continue
        seen.add(username)
        rows.append({
            "username": username,
            "full_name": cols[1] if len(cols) > 1 else "",
            "email": cols[2] if len(cols) > 2 else "",
        })
    return rows, errors


def ensure_portal_user(student, password):
    """학생이 포털에 로그인할 Django 계정 (초기 비밀번호 동일)."""
    User = get_user_model()
    user, created = User.objects.get_or_create(username=student.username)
    if created or not user.has_usable_password():
        user.set_password(password)
    user.first_name = student.full_name[:150]
    user.email = student.email
    user.is_staff = False
    user.save()
    if student.user_id != user.pk:
        student.user = user
        student.save(update_fields=["user"])
    return user


@transaction.atomic
def enroll(rows, cohort="", components=None, created_by=None, queue=True):
    """학생 레코드를 만들고(포트/비밀번호 할당) create 작업을 큐에 넣는다.
    이미 있는 학생은 건너뛴다. 돌려주는 값: (created, skipped)."""
    components = [c for c in ALL_COMPONENTS if c in (components or ALL_COMPONENTS)]
    existing = set(Student.objects.filter(username__in=[r["username"] for r in rows])
                   .values_list("username", flat=True))
    new_rows = [r for r in rows if r["username"] not in existing]
    node_ports = _free_ports("node_port", settings.LAB_NODE_PORT_RANGE, len(new_rows))
    spring_ports = _free_ports("spring_port", settings.LAB_SPRING_PORT_RANGE, len(new_rows))
    created = []
    for row, np, sp in zip(new_rows, node_ports, spring_ports):
        s = Student.objects.create(
            username=row["username"], full_name=row.get("full_name", ""), email=row.get("email", ""),
            cohort=cohort, node_port=np, spring_port=sp, components=components,
            initial_password=generate_password(row["username"]),
        )
        ensure_portal_user(s, s.initial_password)
        if queue:
            queue_job(Job.Kind.CREATE, s, created_by)
        created.append(s)
    return created, sorted(existing)


def queue_job(kind, student=None, created_by=None):
    job = Job.objects.create(
        kind=kind, student=student, username=student.username if student else "",
        created_by=created_by if (created_by and created_by.is_authenticated) else None,
    )
    if student and kind in (Job.Kind.CREATE, Job.Kind.REMOVE, Job.Kind.PURGE):
        Student.objects.filter(pk=student.pk).update(status=Student.Status.PROVISIONING)
    return job


# ---------------------------------------------------------------------------
# 작업 실행 (provision_worker 가 호출)
# ---------------------------------------------------------------------------
def build_payload(job, defer_reload=False):
    s = job.student
    if job.kind == Job.Kind.RELOAD:
        return {"action": "reload"}
    if s is None:
        raise HelperError("job has no student")
    if job.kind == Job.Kind.CREATE:
        return {
            "action": "create", "username": s.username, "password": s.initial_password,
            "node_port": s.node_port, "spring_port": s.spring_port, "components": s.components,
            "force_password_change": settings.LAB_FORCE_PASSWORD_CHANGE,
            "defer_reload": defer_reload,
        }
    if job.kind == Job.Kind.PASSWORD:
        return {
            "action": "password", "username": s.username, "password": s.initial_password,
            "node_port": s.node_port, "components": s.components,
        }
    if job.kind in (Job.Kind.REMOVE, Job.Kind.PURGE):
        return {"action": "remove", "username": s.username,
                "purge": job.kind == Job.Kind.PURGE, "defer_reload": defer_reload}
    raise HelperError(f"unknown job kind {job.kind}")


def run_job(job, defer_reload=False):
    job.status = Job.Status.RUNNING
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at"])
    try:
        result = call_helper(build_payload(job, defer_reload))
        job.result = result
        job.error = result.get("error", "")
        ok = bool(result.get("ok"))
    except HelperError as e:
        job.error = str(e)
        ok = False
    job.status = Job.Status.DONE if ok else Job.Status.FAILED
    job.finished_at = timezone.now()
    job.save()

    s = job.student
    if s is not None:
        errs = job.error or "; ".join(f"{x['step']}: {x['detail']}" for x in job.failed_steps)
        if job.kind == Job.Kind.CREATE:
            s.status = Student.Status.ACTIVE if ok else Student.Status.FAILED
            if ok:
                s.provisioned_at = job.finished_at
        elif job.kind in (Job.Kind.REMOVE, Job.Kind.PURGE):
            s.status = Student.Status.REMOVED if ok else Student.Status.FAILED
            if ok and s.user:
                s.user.is_active = False
                s.user.save(update_fields=["is_active"])
        s.last_error = "" if ok else errs
        s.save()
    log.info("job %s finished: %s", job, job.status)
    return job


# ---------------------------------------------------------------------------
# 서비스 제어 (동기 호출 — 빠름)
# ---------------------------------------------------------------------------
def service_op(student, service, op):
    if service not in SERVICES or service not in student.components:
        raise HelperError(f"service {service} is not enabled for {student.username}")
    if op not in ("start", "stop", "restart", "status"):
        raise HelperError(f"invalid op {op}")
    result = call_helper({"action": "service", "username": student.username,
                          "service": service, "op": op}, timeout=90)
    if not result.get("ok"):
        raise HelperError(result.get("error") or result.get("data", {}).get("output") or "failed")
    return result.get("data", {}).get("output", "")


def service_status(student):
    if student.status != Student.Status.ACTIVE or not student.services:
        return {}
    try:
        result = call_helper({"action": "status", "username": student.username}, timeout=30)
    except HelperError as e:
        return {"error": str(e)}
    if not result.get("ok"):
        return {"error": result.get("error", "status failed")}
    return result.get("data", {}).get("services", {})
