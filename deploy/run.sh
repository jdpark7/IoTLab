#!/bin/bash
# supervisor 에서 호출: 환경파일을 읽고 web 또는 worker 실행
set -a; . /etc/belajarhub/portal.env; set +a
cd /opt/belajarhub-portal
case "$1" in
  web)    exec venv/bin/gunicorn --workers 3 --timeout 120 --bind unix:/run/belajarhub/portal.sock portal.wsgi:application ;;
  worker) exec venv/bin/python manage.py provision_worker ;;
  manage) shift; exec venv/bin/python manage.py "$@" ;;
  *) echo "usage: $0 web|worker|manage <args>"; exit 1 ;;
esac
