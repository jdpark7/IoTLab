from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

COMPONENT_CHOICES = [
    ("php", "PHP site"),
    ("django", "Django (gunicorn)"),
    ("nodejs", "Node-RED"),
    ("spring", "Spring Boot"),
    ("mariadb", "MariaDB database"),
    ("mqtt", "MQTT account"),
]
ALL_COMPONENTS = [c for c, _ in COMPONENT_CHOICES]
SERVICES = ["django", "nodejs", "spring"]

username_validator = RegexValidator(
    r"^[A-Za-z][A-Za-z0-9_-]{1,31}$",
    "Letters, digits, '-' or '_' only; must start with a letter (2-32 chars).",
)


class Student(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROVISIONING = "provisioning", "Provisioning"
        ACTIVE = "active", "Active"
        FAILED = "failed", "Failed"
        REMOVED = "removed", "Removed"

    username = models.CharField(max_length=32, unique=True, validators=[username_validator])
    full_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    cohort = models.CharField("class / cohort", max_length=64, blank=True, db_index=True)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="student",
    )
    node_port = models.PositiveIntegerField(unique=True)
    spring_port = models.PositiveIntegerField(unique=True)
    components = models.JSONField(default=list)
    # Linux / Node-RED / MQTT / MariaDB 공통 초기 비밀번호. 학생에게 전달해야 하므로 보관한다
    # (교수자만 볼 수 있음). 학생이 포털 비밀번호를 바꿔도 이 값은 그대로다.
    initial_password = models.CharField(max_length=128, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    last_error = models.TextField(blank=True)
    imported = models.BooleanField(default=False, help_text="Imported from the legacy shell setup")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    provisioned_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["cohort", "username"]

    def __str__(self):
        return self.username

    @property
    def services(self):
        return [s for s in SERVICES if s in self.components]

    @property
    def site_url(self):
        return f"https://{self.username}.{settings.LAB_DOMAIN}/"

    def links(self):
        base = self.site_url
        out = []
        if "php" in self.components:
            out.append(("PHP site", base))
        if "django" in self.components:
            out.append(("Django", base + "django/"))
        if "nodejs" in self.components:
            out.append(("Node-RED editor", base + "nodejs/"))
            out.append(("Node-RED dashboard", base + "nodejs/ui/"))
        if "spring" in self.components:
            out.append(("Spring Boot", base + "spring/"))
        return out

    @property
    def mqtt_topic(self):
        return f"{settings.LAB_MQTT_TOPIC_PREFIX}/{self.username}/#"


class Job(models.Model):
    class Kind(models.TextChoices):
        CREATE = "create", "Create / re-apply"
        PASSWORD = "password", "Reset password"
        REMOVE = "remove", "Remove configs"
        PURGE = "purge", "Remove + delete data"
        RELOAD = "reload", "Reload services"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    student = models.ForeignKey(Student, null=True, blank=True, on_delete=models.SET_NULL, related_name="jobs")
    username = models.CharField(max_length=32, blank=True)  # 학생 레코드 삭제 후에도 기록 유지
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED, db_index=True)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"#{self.pk} {self.kind} {self.username}"

    @property
    def failed_steps(self):
        return [s for s in self.result.get("steps", []) if not s.get("ok")]
