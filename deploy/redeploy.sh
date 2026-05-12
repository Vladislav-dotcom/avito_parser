#!/usr/bin/env bash
# Полный редеплой avito_parser на VPS: git, venv/pip, restart systemd.
# Вызывается из avito-parser-redeploy-wrapper.sh (flock + лог).
set -euo pipefail

ROOT="${DEPLOY_ROOT:-/opt/avito_parser}"
BRANCH="${DEPLOY_BRANCH:-main}"
UNITS="${SYSTEMD_RESTART_UNITS:-avito-web avito-worker avito-cleanup}"
PIP="${ROOT}/.venv/bin/pip"
TOTAL=5

_step() {
  echo "[${1}/${TOTAL}] ${2}"
}

cd "$ROOT"
export GIT_TERMINAL_PROMPT=0
GIT=(git -c "safe.directory=${ROOT}")

_step 1 "Проверка каталога и git (${ROOT})"
if [[ ! -d "${ROOT}/.git" ]]; then
  echo "Ошибка: ${ROOT} не похож на git-клон (.git отсутствует)." >&2
  exit 1
fi

_step 2 "git fetch + pull (ветка ${BRANCH}, --ff-only)"
"${GIT[@]}" -C "$ROOT" fetch origin "$BRANCH"
"${GIT[@]}" -C "$ROOT" pull --ff-only origin "$BRANCH"

_step 3 "Виртуальное окружение .venv"
if [[ ! -x "${ROOT}/.venv/bin/python" ]]; then
  echo "    .venv нет — создаём: python3 -m venv .venv"
  python3 -m venv "${ROOT}/.venv"
fi

_step 4 "pip install -r requirements.txt"
"$PIP" install -r "${ROOT}/requirements.txt"

_step 5 "systemctl restart: ${UNITS}"
for u in ${UNITS}; do
  echo "    restart ${u}.service"
  systemctl restart "${u}.service" || echo "    предупреждение: не удалось перезапустить ${u}.service (имя юнита или права)" >&2
done

echo "[done] Редеплой завершён $(date -Is)"
