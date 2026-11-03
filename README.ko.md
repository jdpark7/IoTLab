# BelajarHub IoT Lab Portal

[English](README.md)

학생별 IoT 실습 환경(Linux 계정, PHP/Django/Node-RED/Spring 사이트, nginx, supervisor,
sudoers, MQTT, MariaDB)을 웹에서 만들고 관리하는 Django 앱입니다.
`/root` 의 쉘 스크립트들이 하던 일을 그대로 옮겼습니다.

## 구조

```
브라우저 ──▶ nginx ──▶ gunicorn (portal_web, user=belajarhub)
                           │  작업을 DB 큐에 넣음
                           ▼
                     provision_worker (user=belajarhub)
                           │  sudo -n (stdin 으로 JSON 전달)
                           ▼
              /usr/local/sbin/belajarhub-provision   ← root 로 실행되는 유일한 코드
                 useradd · /srv/* · nginx · supervisor · sudoers · Node-RED · mosquitto · MariaDB
```

* **웹앱은 root 로 돌지 않습니다.** root 권한이 필요한 작업은 모두 헬퍼 스크립트 하나에 모았고,
  sudoers 에는 그 스크립트만 허용합니다.
* 헬퍼는 표준 라이브러리만 사용합니다. 모든 입력(username 정규식, 예약어, 포트 범위,
  비밀번호 제어문자)을 검증하고, **`students` 그룹에 속한 계정만** 수정·삭제합니다.
  그래서 포털이 뚫려도 교수자/시스템 계정은 건드릴 수 없습니다.
* sudoers 파일은 `visudo -cf` 로 검사한 뒤에만 설치하고, nginx 설정은 `nginx -t` 가 실패하면 원래대로 되돌립니다.
* 비밀번호는 명령행 인자가 아니라 stdin 으로 전달합니다. 예외는 `mosquitto_passwd -b` 로, 실행되는 동안 잠깐 `ps` 에 보입니다.
* 모든 작업은 **멱등**입니다. "Re-apply" 를 여러 번 눌러도 안전하고, 덮어쓰는 파일은 `.bak` 으로 남깁니다.

### 기존 스크립트와의 대응

| 기존 스크립트 | 헬퍼 단계 |
|---|---|
| create_users.py, change_passwords.sh, change_shell_to_bash.sh | `linux_user` (bash 셸, students 그룹) |
| create_student_dirs.sh, create_php_sites.sh, assign_*_port(s).sh | `directories` |
| deploy_mine_scripts.sh, add_nodejs_control_scripts.sh, setup_spring_supervisor.sh | `directories` (~/bin, /srv/{nodejs,spring}/U/bin 의 *_mine.sh) |
| create_supervisor_django.sh, setup_spring_supervisor.sh, update_supervisior.sh | `supervisor_conf` (timeout 5h, autostart=false) |
| create_sudoers.sh, create_students_sudoers.sh, add_spring_sudoers.sh | `sudoers` → 학생별 파일 `/etc/sudoers.d/belajarhub-<user>` |
| generate_nginx_conf.sh, add_slash.sh | `nginx_conf` |
| setup_node_red_mqtt_students.sh, update_nodered_settings.sh | `nodered_settings`, `mqtt` |
| create_mariadb_users.sh | `mariadb` (root unix_socket 인증) |

생성 결과는 현재 운영 중인 파일과 같습니다(a10029 로 diff 확인). 차이는 세 가지입니다.
맨 위에 "Managed by" 주석이 한 줄 붙고, Node-RED supervisor 설정에 `stopasgroup/killasgroup` 이 추가됩니다.
Node-RED `credentialSecret` 은 이미 있으면 그대로 두고, 새 학생에게만 무작위 값을 씁니다.

## 기능

**교수자 (staff)**
* 학생 일괄 등록: 텍스트 붙여넣기(`username,이름,이메일`, 엑셀에서 복사한 탭 구분도 가능) 또는 CSV 업로드.
  반(cohort)과 구성요소(PHP / Django / Node-RED / Spring / MariaDB / MQTT)를 선택할 수 있습니다.
* 포트(Node-RED 9001~, Spring 8001~)와 비밀번호는 자동으로 배정됩니다.
* 작업 큐와 단계별 결과(어느 단계가 왜 실패했는지)를 볼 수 있습니다.
  여러 명을 한 번에 처리할 때는 nginx/supervisor/mosquitto reload 를 마지막에 한 번만 합니다.
* 학생별: 서비스 시작·정지·재시작·상태, 구성 변경 후 재적용, 새 비밀번호 발급, 제거(설정만 / 데이터까지)
* 계정 정보 CSV 내보내기 (반별)

**학생**
* 포털 로그인 후 내 사이트 URL, SSH/MQTT/MariaDB 접속 정보, 포트 확인
* 내 Django / Node-RED / Spring 서비스 시작·정지·재시작 (본인 것만)

화면은 인도네시아 학생과 함께 쓸 수 있도록 영어로 되어 있습니다.

## 서버 설치

```bash
# 이 폴더를 서버로 복사한 뒤
sudo ./deploy/install.sh
sudo -u belajarhub /opt/belajarhub-portal/deploy/run.sh manage createsuperuser
```

* 설정 파일: `/etc/belajarhub/portal.env` (웹앱), `/etc/belajarhub/provision.json` (헬퍼: 도메인, php-fpm 소켓, 포트 범위 등)
* `portal.belajarhub.id` DNS 레코드가 필요합니다. 인증서가 이 이름을 포함하지 않으면
  `deploy/nginx-portal.conf` 의 인증서 경로를 바꾸세요.
* 비밀번호 방식: `LAB_PASSWORD_MODE=random`(기본, 10자 무작위) 또는 기존 방식인 `{username}*01`.

### 기존 학생 60명 가져오기

포털 DB 에 기록만 남기고 서버 설정은 바꾸지 않습니다.
포트는 기존 스크립트와 같은 규칙(username 파일의 N 번째 → 9000+N / 8000+N)으로 기록하므로 새 학생과 겹치지 않습니다.

```bash
sudo -u belajarhub /opt/belajarhub-portal/deploy/run.sh manage import_students /root/username \
     --cohort "IoT 2026-1" --password-template "{username}*01"
# 포털이 이 계정들을 관리할 수 있도록 students 그룹에 추가
while read u; do [ -n "$u" ] && sudo usermod -aG students "$u"; done < /root/username
```

가져온 학생의 sudoers 규칙은 기존 공용 파일 `/etc/sudoers.d/students-supervisor` 에 그대로 남습니다.
"Re-apply" 를 하면 학생별 파일이 하나 더 생기는데, 같은 규칙이 겹치는 것이라 문제는 없습니다.
학생을 제거하면 공용 파일에서도 그 학생 줄을 지웁니다.

## 개발 / 테스트 (root 불필요)

헬퍼는 `BELAJARHUB_SANDBOX=<dir>` 이 설정되면 모든 경로를 그 디렉터리 아래로 바꾸고,
외부 명령은 실행하지 않은 채 `<dir>/commands.log` 에 기록만 합니다.

```bash
pip install -r requirements.txt
PORTAL_DEBUG=1 python manage.py test labs          # 샌드박스로 헬퍼까지 실제 실행

# 로컬에서 직접 써 보기
export PORTAL_DEBUG=1 BELAJARHUB_SANDBOX=/tmp/sb LAB_PROVISION_CMD="python3 provisioner/belajarhub-provision"
python manage.py migrate && python manage.py createsuperuser
python manage.py provision_worker &      # 작업 큐 처리
python manage.py runserver
```

헬퍼 직접 호출 예:
```bash
echo '{"action":"status","username":"a10029"}' | sudo /usr/local/sbin/belajarhub-provision
```

## 남은 결정 사항 / 주의

* 학생의 초기 비밀번호는 포털 DB 에 평문으로 저장됩니다. 교수자 화면과 학생 본인 화면에만 보입니다.
  SSH·Node-RED·MQTT·MariaDB 가 같은 비밀번호를 쓰고 학생에게 전달해야 하기 때문입니다.
  DB 파일(`/var/lib/belajarhub/portal.sqlite3`)은 `belajarhub` 사용자만 읽을 수 있습니다.
* 학생이 `passwd` 로 SSH 비밀번호를 바꾸면 Linux 계정에만 적용되고, 다른 서비스는 초기 비밀번호를 계속 씁니다(기존과 같음).
* 비밀번호 확인(`/etc/shadow`) 권한은 포털에 주지 않으려고, 포털 로그인은 Linux 비밀번호가 아니라 별도 Django 계정을 씁니다.
  초기 비밀번호는 같습니다.
