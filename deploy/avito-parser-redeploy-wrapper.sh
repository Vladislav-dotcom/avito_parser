#!/usr/bin/env bash
# Обёртка: flock + append-лог, затем redeploy.sh
set -euo pipefail

ROOT="${DEPLOY_ROOT:-/opt/avito_parser}"
LOCK="${REDEPLOY_LOCK_FILE:-/var/run/avito-parser-redeploy.lock}"
LOG="${REDEPLOY_LOG_FILE:-/var/log/avito-parser-redeploy.log}"

exec >>"$LOG" 2>&1
echo "[$(date -Is)] webhook: запуск обёртки redeploy"

(
  flock -n 9 || { echo "[$(date -Is)] пропуск: занят lock ${LOCK}"; exit 0; }
  echo "[$(date -Is)] lock получен, старт redeploy.sh"
  exec bash "${ROOT}/deploy/redeploy.sh"
) 9>"$LOCK"
