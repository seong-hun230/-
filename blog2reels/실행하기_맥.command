#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "[!] Python 3 가 없습니다. https://www.python.org/downloads/ 에서 설치하세요."
  read -n 1; exit 1
fi
echo "필요한 프로그램 설치 중… (처음 한 번만, 1~2분)"
python3 -m pip install -r requirements.txt --quiet --disable-pip-version-check --user 2>/dev/null \
  || python3 -m pip install -r requirements.txt --quiet --disable-pip-version-check --break-system-packages
python3 app.py
