"""큐에 쌓인 프로비저닝 작업을 순서대로 실행한다 (supervisor 로 상시 실행).

    python manage.py provision_worker          # 계속 실행
    python manage.py provision_worker --once   # 대기 작업만 처리하고 종료
"""
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from labs.models import Job
from labs.services import HelperError, call_helper, run_job

BATCHABLE = (Job.Kind.CREATE, Job.Kind.REMOVE, Job.Kind.PURGE)


class Command(BaseCommand):
    help = "Run queued provisioning jobs"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=float, default=2.0)

    def handle(self, *args, **opts):
        # 이전에 비정상 종료되어 running 으로 남은 작업은 실패 처리
        stale = Job.objects.filter(status=Job.Status.RUNNING).update(
            status=Job.Status.FAILED, error="worker restarted while job was running",
            finished_at=timezone.now())
        if stale:
            self.stderr.write(f"marked {stale} stale job(s) as failed")
        while True:
            close_old_connections()
            processed = self.process_queue()
            if opts["once"]:
                break
            if not processed:
                time.sleep(opts["interval"])

    def process_queue(self):
        jobs = list(Job.objects.filter(status=Job.Status.QUEUED).select_related("student").order_by("id")[:200])
        if not jobs:
            return 0
        # 여러 학생을 한꺼번에 만들 때는 nginx/supervisor/mosquitto reload 를 마지막에 한 번만
        batch = sum(1 for j in jobs if j.kind in BATCHABLE) > 1
        for job in jobs:
            job.refresh_from_db()
            if job.status != Job.Status.QUEUED:
                continue
            run_job(job, defer_reload=batch and job.kind in BATCHABLE)
            self.stdout.write(f"{job} -> {job.status}")
        if batch:
            try:
                r = call_helper({"action": "reload"})
                self.stdout.write(f"reload -> {'ok' if r.get('ok') else r}")
            except HelperError as e:
                self.stderr.write(f"reload failed: {e}")
        return len(jobs)
