#!/bin/bash
# BelajarHub IoT Lab Portal 설치 (서버에서 root 로 실행, 여러 번 실행해도 안전)
#   sudo ./deploy/install.sh
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
APP=/opt/belajarhub-portal
ETC=/etc/belajarhub

[ "$EUID" -eq 0 ] || { echo "root 권한으로 실행하세요: sudo $0"; exit 1; }
command -v python3 >/dev/null || { echo "python3 필요"; exit 1; }
python3 -c 'import venv, ensurepip' 2>/dev/null || apt-get install -y python3-venv
command -v htpasswd >/dev/null || apt-get install -y apache2-utils

echo "== 1. 사용자/그룹"
id belajarhub >/dev/null 2>&1 || useradd --system --home /var/lib/belajarhub --shell /usr/sbin/nologin belajarhub
getent group students >/dev/null || groupadd students
install -d -o belajarhub -g belajarhub -m 750 /var/lib/belajarhub /var/log/belajarhub
install -d -o belajarhub -g www-data -m 750 /run/belajarhub
# /run 은 재부팅 시 사라지므로 tmpfiles 등록
echo "d /run/belajarhub 0750 belajarhub www-data -" > /etc/tmpfiles.d/belajarhub.conf

echo "== 2. 프로비저닝 헬퍼 (root 전용)"
install -o root -g root -m 755 "$SRC/provisioner/belajarhub-provision" /usr/local/sbin/belajarhub-provision
install -d -o root -g root -m 755 "$ETC"
[ -f "$ETC/provision.json" ] || install -o root -g root -m 644 "$SRC/deploy/provision.json.example" "$ETC/provision.json"

echo "== 3. sudoers"
TMP=$(mktemp)
cp "$SRC/deploy/sudoers-belajarhub" "$TMP"
visudo -cf "$TMP"
install -o root -g root -m 440 "$TMP" /etc/sudoers.d/belajarhub-portal
rm -f "$TMP"

echo "== 4. 앱 복사 + venv"
mkdir -p "$APP"
cp -a "$SRC/manage.py" "$SRC/requirements.txt" "$SRC/portal" "$SRC/labs" "$SRC/deploy" "$SRC/provisioner" "$APP/"
[ -d "$APP/venv" ] || python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install -q --upgrade pip
"$APP/venv/bin/pip" install -q -r "$APP/requirements.txt"
chown -R root:root "$APP"
chmod 755 "$APP/deploy/run.sh"

echo "== 5. 환경파일"
if [ ! -f "$ETC/portal.env" ]; then
    KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')
    sed "s|^PORTAL_SECRET_KEY=.*|PORTAL_SECRET_KEY=$KEY|" "$SRC/deploy/portal.env.example" > "$ETC/portal.env"
fi
chown root:belajarhub "$ETC/portal.env"; chmod 640 "$ETC/portal.env"

echo "== 6. DB / static"
install -d -o belajarhub -g belajarhub -m 755 "$APP/staticfiles"
sudo -u belajarhub "$APP/deploy/run.sh" manage migrate --noinput
sudo -u belajarhub "$APP/deploy/run.sh" manage collectstatic --noinput >/dev/null

echo "== 7. supervisor / nginx"
install -m 644 "$SRC/deploy/supervisor-portal.conf" /etc/supervisor/conf.d/belajarhub_portal.conf
[ -f /etc/nginx/conf.d/portal.conf ] || install -m 644 "$SRC/deploy/nginx-portal.conf" /etc/nginx/conf.d/portal.conf
supervisorctl reread
supervisorctl update
supervisorctl restart portal_web portal_worker
nginx -t && systemctl reload nginx

cat <<MSG

설치 완료.
  관리자 계정 만들기 : sudo -u belajarhub $APP/deploy/run.sh manage createsuperuser
  기존 학생 가져오기 : sudo -u belajarhub $APP/deploy/run.sh manage import_students /root/username --cohort "IoT 2026-1"
                      while read u; do [ -n "\$u" ] && usermod -aG students "\$u"; done < /root/username
  접속              : https://portal.belajarhub.id/   (DNS / 인증서에 portal 서브도메인 필요)
MSG
