import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Job, Student
from .services import enroll, parse_roster

HELPER = Path(__file__).resolve().parent.parent / "provisioner" / "belajarhub-provision"


class RosterTests(TestCase):
    def test_parse(self):
        rows, errors = parse_roster("username,name\na10301,Budi\n\n# c\na10302\tSiti\tsiti@x.id\nbad name\na10301\n")
        self.assertEqual([r["username"] for r in rows], ["a10301", "a10302"])
        self.assertEqual(rows[1]["email"], "siti@x.id")
        self.assertEqual(len(errors), 2)


class SandboxHelperMixin:
    """실제 헬퍼를 샌드박스(BELAJARHUB_SANDBOX)로 실행한다 — root 불필요."""

    def setUp(self):
        self.sandbox = tempfile.TemporaryDirectory()
        self.sb = Path(self.sandbox.name)
        self.env = mock.patch.dict(os.environ, {"BELAJARHUB_SANDBOX": str(self.sb)})
        self.env.start()
        self.cmd = override_settings(LAB_PROVISION_CMD=[sys.executable, str(HELPER)])
        self.cmd.enable()

    def tearDown(self):
        self.cmd.disable()
        self.env.stop()
        self.sandbox.cleanup()


class ProvisionFlowTests(SandboxHelperMixin, TestCase):
    def test_enroll_and_worker(self):
        created, skipped = enroll([{"username": "t20001", "full_name": "Test"}, {"username": "t20002"}],
                                  cohort="C1")
        self.assertEqual(len(created), 2)
        self.assertEqual(Job.objects.filter(status="queued").count(), 2)
        ports = sorted(Student.objects.values_list("node_port", flat=True))
        self.assertEqual(ports, [9001, 9002])

        call_command("provision_worker", "--once", stdout=open(os.devnull, "w"))
        for s in Student.objects.all():
            self.assertEqual(s.status, "active", s.last_error)
        nginx = (self.sb / "etc/nginx/conf.d/t20002.conf").read_text()
        self.assertIn("proxy_pass http://127.0.0.1:9002/;", nginx)
        self.assertIn("server_name t20002.belajarhub.id;", nginx)
        sup = (self.sb / "etc/supervisor/conf.d/spring_t20001.conf").read_text()
        self.assertIn("--server.port=8001", sup)
        acl = (self.sb / "etc/mosquitto/acl").read_text()
        self.assertIn("user t20001\ntopic readwrite unsia/t20001/#", acl)
        # batch 모드: reload 는 마지막에 한 번만
        log = (self.sb / "commands.log").read_text()
        self.assertEqual(log.count("systemctl reload nginx"), 1)

        # 다시 등록하면 건너뜀
        created, skipped = enroll([{"username": "t20001"}])
        self.assertEqual((created, skipped), ([], ["t20001"]))

    def test_remove(self):
        (s,), _ = enroll([{"username": "t20003"}])
        call_command("provision_worker", "--once", stdout=open(os.devnull, "w"))
        Job.objects.create(kind=Job.Kind.REMOVE, student=s, username=s.username)
        call_command("provision_worker", "--once", stdout=open(os.devnull, "w"))
        s.refresh_from_db()
        self.assertEqual(s.status, "removed")
        self.assertFalse((self.sb / "etc/nginx/conf.d/t20003.conf").exists())
        self.assertNotIn("t20003", (self.sb / "etc/mosquitto/acl").read_text())


class ImportTests(TestCase):
    def test_import_assigns_legacy_ports(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write("a10029\na10039\n\na10057\n")
        call_command("import_students", f.name, "--cohort", "old", stdout=open(os.devnull, "w"))
        os.unlink(f.name)
        s = Student.objects.get(username="a10057")
        self.assertEqual((s.node_port, s.spring_port, s.status), (9003, 8003, "active"))
        self.assertEqual(s.initial_password, "a10057*01")
        # 새 학생은 기존 포트를 피해서 배정
        (new,), _ = enroll([{"username": "n30001"}], queue=False)
        self.assertEqual(new.node_port, 9004)


class ViewTests(SandboxHelperMixin, TestCase):
    def setUp(self):
        super().setUp()
        User = get_user_model()
        self.staff = User.objects.create_user("prof", password="pw-prof-123", is_staff=True)
        (self.s,), _ = enroll([{"username": "t20010"}])
        (self.other,), _ = enroll([{"username": "t20011"}])
        call_command("provision_worker", "--once", stdout=open(os.devnull, "w"))
        self.s.refresh_from_db()

    def test_student_sees_own_lab_and_controls_service(self):
        self.client.login(username="t20010", password=self.s.initial_password)
        r = self.client.get(reverse("my_lab"))
        self.assertContains(r, "https://t20010.belajarhub.id/nodejs/")
        self.assertNotContains(r, "t20011")
        r = self.client.post(reverse("my_lab"), {"service": "nodejs", "op": "start"}, follow=True)
        self.assertContains(r, "nodejs start")
        self.assertIn("supervisorctl start nodejs_t20010", (self.sb / "commands.log").read_text())

    def test_student_cannot_open_staff_pages(self):
        self.client.login(username="t20010", password=self.s.initial_password)
        for name in ("dashboard", "enroll", "jobs", "export_csv"):
            r = self.client.get(reverse(name))
            self.assertEqual(r.status_code, 302, name)
        r = self.client.get(reverse("student_detail", args=["t20011"]))
        self.assertEqual(r.status_code, 302)

    def test_staff_pages(self):
        self.client.login(username="prof", password="pw-prof-123")
        self.assertContains(self.client.get(reverse("dashboard")), "t20011")
        self.assertContains(self.client.get(reverse("student_detail", args=["t20010"])), "nodejs_t20010")
        self.assertContains(self.client.get(reverse("jobs")), "Create")
        csv = self.client.get(reverse("export_csv")).content.decode()
        self.assertIn(self.s.initial_password, csv)
        r = self.client.post(reverse("enroll"), {"roster": "t20020,New One\n", "cohort": "C2",
                                                 "components": ["php", "nodejs", "mqtt"]})
        self.assertRedirects(r, reverse("jobs"))
        self.assertEqual(Student.objects.get(username="t20020").components, ["php", "nodejs", "mqtt"])
        r = self.client.post(reverse("student_remove", args=["t20011"]), {"confirm": "wrong"})
        self.assertContains(r, "does not match")
