"""기존 쉘 스크립트로 만든 학생들을 포털 DB 로 가져온다 (설정 파일은 건드리지 않음).

기존 스크립트는 username 파일의 줄 순서대로 포트를 배정했다:
    N 번째 학생 → Node-RED 9000+N, Spring 8000+N
같은 규칙으로 포트를 기록해 새 학생과 충돌하지 않게 한다.

    python manage.py import_students /root/username --cohort "IoT 2026" \
        --password-template "{username}*01"
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from labs.models import ALL_COMPONENTS, Student
from labs.services import ensure_portal_user, parse_roster


class Command(BaseCommand):
    help = "Import students that were set up by the legacy shell scripts"

    def add_arguments(self, parser):
        parser.add_argument("username_file")
        parser.add_argument("--cohort", default="")
        parser.add_argument("--node-base", type=int, default=9001)
        parser.add_argument("--spring-base", type=int, default=8001)
        parser.add_argument("--password-template", default="{username}*01",
                            help="initial password the legacy scripts used (shown to staff)")
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **o):
        try:
            text = open(o["username_file"], encoding="utf-8").read()
        except OSError as e:
            raise CommandError(e)
        rows, errors = parse_roster(text)
        for e in errors:
            self.stderr.write(e)
        added = 0
        for idx, row in enumerate(rows):
            u = row["username"]
            np, sp = o["node_base"] + idx, o["spring_base"] + idx
            if Student.objects.filter(username=u).exists():
                self.stdout.write(f"[SKIP] {u} already in portal")
                continue
            clash = Student.objects.filter(node_port=np).first() or Student.objects.filter(spring_port=sp).first()
            if clash:
                raise CommandError(f"port clash for {u}: {np}/{sp} already used by {clash}")
            self.stdout.write(f"[ADD]  {u} node={np} spring={sp}")
            if o["dry_run"]:
                continue
            pw = o["password_template"].format(username=u)
            s = Student.objects.create(
                username=u, cohort=o["cohort"], node_port=np, spring_port=sp,
                components=list(ALL_COMPONENTS), initial_password=pw,
                status=Student.Status.ACTIVE, imported=True,
            )
            ensure_portal_user(s, pw)
            added += 1
        self.stdout.write(self.style.SUCCESS(f"imported {added} student(s)"))
        if added:
            self.stdout.write(
                "다음 단계 (root): 가져온 학생을 students 그룹에 넣어야 포털에서 제어할 수 있습니다\n"
                f"  while read u; do [ -n \"$u\" ] && usermod -aG students \"$u\"; done < {o['username_file']}"
            )
