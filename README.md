# BelajarHub IoT Lab Portal

[한국어](README.ko.md)

A Django app for creating and managing a separate IoT lab environment for each student from the web.
Each environment includes a Linux account, PHP/Django/Node-RED/Spring sites, nginx, supervisor,
sudoers, MQTT and MariaDB. It replaces the shell scripts that used to be run by hand from `/root`.

## Architecture

```
browser ──▶ nginx ──▶ gunicorn (portal_web, user=belajarhub)
                           │  puts jobs on a DB queue
                           ▼
                     provision_worker (user=belajarhub)
                           │  sudo -n (JSON on stdin)
                           ▼
              /usr/local/sbin/belajarhub-provision   ← the only code that runs as root
                 useradd · /srv/* · nginx · supervisor · sudoers · Node-RED · mosquitto · MariaDB
```

* **The web app never runs as root.** Every privileged operation lives in one helper script,
  and sudoers allows only that script.
* The helper uses only the Python standard library. It validates every input: the username pattern,
  reserved names, port ranges and control characters in passwords. It modifies or removes
  **only accounts in the `students` group**, so a compromised portal still cannot touch
  staff or system accounts.
* sudoers files are installed only after they pass `visudo -cf`. An nginx config is rolled back
  if `nginx -t` fails.
* Passwords go to commands over stdin, not as command-line arguments. The one exception is
  `mosquitto_passwd -b`, where the password is briefly visible in `ps` while it runs.
* Every operation is **idempotent**. You can click "Re-apply" as often as you like, and any file
  that gets overwritten is kept as `.bak`.

### Mapping from the old scripts

| Old script | Helper step |
|---|---|
| create_users.py, change_passwords.sh, change_shell_to_bash.sh | `linux_user` (bash shell, `students` group) |
| create_student_dirs.sh, create_php_sites.sh, assign_*_port(s).sh | `directories` |
| deploy_mine_scripts.sh, add_nodejs_control_scripts.sh, setup_spring_supervisor.sh | `directories` (`*_mine.sh` in ~/bin and /srv/{nodejs,spring}/U/bin) |
| create_supervisor_django.sh, setup_spring_supervisor.sh, update_supervisior.sh | `supervisor_conf` (5h timeout, autostart=false) |
| create_sudoers.sh, create_students_sudoers.sh, add_spring_sudoers.sh | `sudoers` → one file per student, `/etc/sudoers.d/belajarhub-<user>` |
| generate_nginx_conf.sh, add_slash.sh | `nginx_conf` |
| setup_node_red_mqtt_students.sh, update_nodered_settings.sh | `nodered_settings`, `mqtt` |
| create_mariadb_users.sh | `mariadb` (root over unix_socket auth) |

The generated files match the configs in production (checked by diffing them for a10029). There are three differences:
* Each file starts with a one-line "Managed by" comment.
* The Node-RED supervisor config adds `stopasgroup/killasgroup`, so the child processes
  started under `timeout` are stopped too.
* An existing Node-RED `credentialSecret` is kept, and only new students get a random one.

## Features

**Staff**
* Bulk enrollment: paste lines of `username,full name,email` (tab-separated text copied from a
  spreadsheet also works) or upload a CSV. You choose the class (cohort) and the components:
  PHP / Django / Node-RED / Spring / MariaDB / MQTT.
* Ports (Node-RED 9001+, Spring 8001+) and passwords are assigned automatically.
* A job queue shows the result of each step, including which step failed and why.
  When many students are processed at once, nginx/supervisor/mosquitto are reloaded only once, at the end.
* Per student: start / stop / restart / status of services, re-apply after changing the configuration,
  issue a new password, and remove (configs only, or data too).
* Export credentials as CSV, filtered by class.

**Students**
* Log in to the portal to see your site URLs, SSH / MQTT / MariaDB connection details and your ports.
* Start, stop and restart your own Django / Node-RED / Spring services (and nobody else's).

The UI is in English, so Indonesian students can use it too.

## Server installation

```bash
git clone https://github.com/jdpark7/IoTLab
cd IoTLab
sudo ./deploy/install.sh
sudo -u belajarhub /opt/belajarhub-portal/deploy/run.sh manage createsuperuser
```

* Config files: `/etc/belajarhub/portal.env` (web app) and `/etc/belajarhub/provision.json`
  (helper: domain, php-fpm socket, port ranges, etc.).
* A DNS record for `portal.belajarhub.id` is required. If your certificate does not cover that name,
  change the certificate paths in `deploy/nginx-portal.conf`.
* Password mode: `LAB_PASSWORD_MODE=random` (default, 10 random characters) or the old scheme `{username}*01`.

### Importing existing students

This only records the students in the portal database. It does not change anything on the server.
Ports follow the same rule as the old scripts (the Nth line of the username file → 9000+N / 8000+N),
so they never collide with new students.

```bash
sudo -u belajarhub /opt/belajarhub-portal/deploy/run.sh manage import_students /root/username \
     --cohort "IoT 2026-1" --password-template "{username}*01"
# Add them to the students group so the portal is allowed to manage them
while read u; do [ -n "$u" ] && sudo usermod -aG students "$u"; done < /root/username
```

The sudoers rules of imported students stay in the old shared file `/etc/sudoers.d/students-supervisor`.
"Re-apply" adds a per-student file on top of that. The rules are duplicates, which is harmless.
Removing a student also deletes that student's lines from the shared file.

## Development and testing (no root needed)

When `BELAJARHUB_SANDBOX=<dir>` is set, the helper moves every path under that directory and does not
run any external command. It only logs the commands to `<dir>/commands.log`.

```bash
pip install -r requirements.txt
PORTAL_DEBUG=1 python manage.py test labs          # also runs the real helper in the sandbox

# Try it locally
export PORTAL_DEBUG=1 BELAJARHUB_SANDBOX=/tmp/sb LAB_PROVISION_CMD="python3 provisioner/belajarhub-provision"
python manage.py migrate && python manage.py createsuperuser
python manage.py provision_worker &      # processes the job queue
python manage.py runserver
```

Calling the helper directly:
```bash
echo '{"action":"status","username":"a10029"}' | sudo /usr/local/sbin/belajarhub-provision
```

## Notes and open decisions

* Students' initial passwords are stored in plain text in the portal database. They are shown only on
  staff pages and on the student's own page. They have to be stored because SSH, Node-RED, MQTT and
  MariaDB all use the same password and it must be handed to the student.
  The database file (`/var/lib/belajarhub/portal.sqlite3`) is readable only by the `belajarhub` user.
* If a student changes their SSH password with `passwd`, only the Linux account changes. The other
  services keep using the initial password, as before.
* Portal login uses its own Django account, not the Linux password, so the portal never needs access to
  `/etc/shadow`. The initial password is the same for both.

## License

GPL-3.0. See [LICENSE](LICENSE).
