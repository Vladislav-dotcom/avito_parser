# AI-анализатор парсинга с Avito

Сервис на Flask для загрузки XLSX, построчного AI-анализа колонки `Описание` через RouterAI и скачивания готового XLSX с новыми колонками.

## Что делает сервис

### Обязательные колонки во входном XLSX
- `Наименование`
- `Цена`
- `Валюта`
- `Кол-во в наличии`
- `Раздел`
- `Категория`
- `Описание`

### Какие колонки добавляются в выходной XLSX
- `Бренд`
- `Артикул`
- `Цена`
- `Кол-во`
- `Состояние`

## Архитектура (без Redis)

- `Flask` отвечает за UI и API (`upload/status/download`)
- `SQLite` хранит очередь задач и прогресс
- `worker.py --mode worker` обрабатывает очередь последовательно
- `worker.py --mode cleanup` удаляет старые файлы по расписанию (TTL)

## Технологии

- Backend: `Flask`, `Flask-Cors`
- XLSX: `pandas`, `openpyxl`
- AI: `httpx` (синхронные запросы)
- Валидация: `pydantic`
- Хранение очереди/статусов: `sqlite3`
- Логи: `logging` + `RotatingFileHandler` (JSON)

## Переменные окружения

Создай файл `.env` в корне проекта (можно взять `.env.example`):

```env
FLASK_ENV=development
SECRET_KEY=change-me
ROUTERAI_API_KEY=your_routerai_key
ROUTERAI_BASE_URL=https://routerai.ru/api/v1
ROUTERAI_MODEL=google/gemini-3.1-flash-lite-preview
SQLITE_DB_PATH=storage/jobs.db
MAX_FILE_SIZE_MB=10
FILE_TTL_SECONDS=86400
DELETE_AFTER_DOWNLOAD_SECONDS=1800
CLEANUP_INTERVAL_SECONDS=300
AI_REQUEST_TIMEOUT_SECONDS=45
AI_RETRIES=2
AI_RETRY_DELAY_SECONDS=1.5
JOB_POLL_INTERVAL_SECONDS=1.0
STALE_PROCESSING_SECONDS=7200
```

Документация RouterAI: [routerai.ru/docs/guides/overview/quickstart](https://routerai.ru/docs/guides/overview/quickstart)

## Запуск на Windows (ПК разработчика)

### 1. Установка зависимостей

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Запуск сервиса (3 терминала)

Терминал 1 (web):

```powershell
.venv\Scripts\Activate.ps1
python app.py
```

Терминал 2 (worker):

```powershell
.venv\Scripts\Activate.ps1
python worker.py --mode worker
```

Терминал 3 (cleanup):

```powershell
.venv\Scripts\Activate.ps1
python worker.py --mode cleanup
```

Открыть в браузере:
- `http://127.0.0.1:5000`

### 3. Тесты

```powershell
.venv\Scripts\Activate.ps1
python -m pytest -q
```

## Продакшн на Ubuntu 22.04

Рекомендуемая схема: `gunicorn + systemd + nginx` (SQLite локально в приложении).

### 1. Установка системных пакетов

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx
```

### 2. Деплой приложения

```bash
sudo mkdir -p /opt/avito_parser
sudo chown -R $USER:$USER /opt/avito_parser
cd /opt/avito_parser

# Скопируй файлы проекта в эту директорию
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`gunicorn` входит в `requirements.txt`. Создай `.env` в `/opt/avito_parser/.env` и укажи реальный `ROUTERAI_API_KEY`.

### 3. Проверка вручную (до systemd)

```bash
source .venv/bin/activate
python app.py
```

Проверить:
- `http://SERVER_IP:5000`

### 4. systemd: web (gunicorn)

`/etc/systemd/system/avito-web.service`

```ini
[Unit]
Description=Avito Parser Web (Gunicorn)
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/avito_parser
EnvironmentFile=/opt/avito_parser/.env
ExecStart=/opt/avito_parser/.venv/bin/gunicorn -w 1 -b 127.0.0.1:8000 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 5. systemd: worker

`/etc/systemd/system/avito-worker.service`

```ini
[Unit]
Description=Avito Parser SQLite Worker
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/avito_parser
EnvironmentFile=/opt/avito_parser/.env
ExecStart=/opt/avito_parser/.venv/bin/python worker.py --mode worker
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 6. systemd: cleanup

`/etc/systemd/system/avito-cleanup.service`

```ini
[Unit]
Description=Avito Parser Cleanup Loop
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/avito_parser
EnvironmentFile=/opt/avito_parser/.env
ExecStart=/opt/avito_parser/.venv/bin/python worker.py --mode cleanup
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Применить:

```bash
sudo systemctl daemon-reload
sudo systemctl enable avito-web avito-worker avito-cleanup
sudo systemctl start avito-web avito-worker avito-cleanup
sudo systemctl status avito-web avito-worker avito-cleanup
```

### 6.1 Анти-OOM настройки (рекомендуется для 2-4 GB RAM)

1) Ограничь веб-процесс одним воркером `gunicorn`:
- в `avito-web.service` уже указан `-w 1` (см. `ExecStart` выше)

2) Держи по одному фоновому процессу:
- один `avito-worker.service` (`worker.py --mode worker`)
- один `avito-cleanup.service` (`worker.py --mode cleanup`)
- не запускай вручную дополнительные копии этих процессов

3) Увеличь swap до 2 GB (можно 1 GB, но лучше 2 GB):

```bash
# если swap уже есть, отключаем и удаляем старый файл
sudo swapoff -a || true
sudo rm -f /swapfile

# создаем новый swap 2 GB
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# делаем swap постоянным после ребута
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# проверка
free -h
swapon --show
```

### 7. Nginx reverse proxy

`/etc/nginx/sites-available/avito-parser`

```nginx
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Активировать:

```bash
sudo ln -s /etc/nginx/sites-available/avito-parser /etc/nginx/sites-enabled/avito-parser
sudo nginx -t
sudo systemctl restart nginx
```

## Автодеплой по push (GitHub → VPS)

Репозиторий: [Vladislav-dotcom/avito_parser](https://github.com/Vladislav-dotcom/avito_parser). Прод: **`/opt/avito_parser`**.

**Не пересекается с `ai_parser` на том же сервере:** префикс **`/hooks/avito-parser/`**, порт слушателя **`9848`** (у `ai_parser` — `9847`).

| Файл в `deploy/` | Назначение |
|-------------------|------------|
| `redeploy.sh` | `git pull --ff-only`, `.venv` + `pip`, `systemctl restart` из `SYSTEMD_RESTART_UNITS` |
| `avito-parser-redeploy-wrapper.sh` | `flock` + лог `/var/log/avito-parser-redeploy.log` |
| `github_webhook_listener.py` | HMAC `X-Hub-Signature-256`, ответ **202**, редеплой в фоне |
| `avito-parser-github-hook.service` | systemd, `EnvironmentFile=/etc/avito-parser-deploy-hook.env` |
| `avito-parser-deploy-hook.env.example` | шаблон секрета, ветки, порта, юнитов |
| `nginx-avito-parser-github-hook.conf` | `location /hooks/avito-parser/` → `127.0.0.1:9848` |
| `apache-avito-parser-github-hook-snippet.conf.example` | `ProxyPass` для Apache на `:80` |

### Пошагово на VPS (SSH, копировать блоки)

```bash
ssh root@37.230.116.197
```

**0. Имена systemd (если отличаются от `avito-web` / `avito-worker` / `avito-cleanup`)**

```bash
systemctl list-units --type=service --state=running | grep -i avito
```

Дальше в примерах используются три юнита из README выше.

**1. Остановка приложения**

```bash
sudo systemctl stop avito-web avito-worker avito-cleanup
```

**2. Бэкап**

```bash
sudo cp -a /opt/avito_parser "/opt/avito_parser.bak.$(date +%Y%m%d)"
ls -la /opt/avito_parser.bak.*
```

**3. Git и клон во временный каталог**

```bash
sudo apt-get install -y git
sudo git clone https://github.com/Vladislav-dotcom/avito_parser.git /opt/avito_parser_git
```

**4. Перенос `.env`, SQLite, `storage/` из бэкапа**

Подставьте свой каталог бэкапа в `BAK` (из шага 2).

```bash
BAK=/opt/avito_parser.bak.20260512
NEW=/opt/avito_parser_git
export BAK NEW
test -d "$BAK" && test -d "$NEW" || { echo "Проверь BAK и NEW"; exit 1; }

sudo test -f "$BAK/.env" && sudo cp -a "$BAK/.env" "$NEW/.env" || echo "Нет .env в бэкапе — создай вручную"
sudo test -d "$BAK/storage" && sudo cp -a "$BAK/storage" "$NEW/storage" || echo "Нет storage в бэкапе"
```

**5. Подмена каталогов**

```bash
sudo mv /opt/avito_parser /opt/avito_parser_old
sudo mv /opt/avito_parser_git /opt/avito_parser
```

**6. Владелец (как в unit: обычно `www-data`)**

```bash
export APP_USER=www-data
sudo chown -R "$APP_USER:$APP_USER" /opt/avito_parser
```

**7. Права на деплой-скрипты и зависимости**

```bash
sudo chmod +x /opt/avito_parser/deploy/redeploy.sh /opt/avito_parser/deploy/avito-parser-redeploy-wrapper.sh
sudo -u "$APP_USER" bash -c 'cd /opt/avito_parser && (test -x .venv/bin/pip && .venv/bin/pip install -r requirements.txt) || (python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)'
```

**8. Учётные данные GitHub для `git pull` от root (без TTY)**

```bash
sudo git config --global credential.helper store
sudo sh -c 'printf "https://ВАШ_ЛОГИН_GITHUB:ВАШ_PAT@github.com\n" > /root/.git-credentials'
sudo chmod 600 /root/.git-credentials
sudo git config --global --add safe.directory /opt/avito_parser
sudo git -c safe.directory=/opt/avito_parser -C /opt/avito_parser ls-remote origin HEAD
```

**9. Секрет webhook и env**

```bash
openssl rand -hex 32
sudo cp /opt/avito_parser/deploy/avito-parser-deploy-hook.env.example /etc/avito-parser-deploy-hook.env
sudo chmod 600 /etc/avito-parser-deploy-hook.env
sudo nano /etc/avito-parser-deploy-hook.env
```

В файле: `GITHUB_WEBHOOK_SECRET` (тот же hex + тот же в GitHub Webhook), `DEPLOY_BRANCH=main`, `DEPLOY_ROOT=/opt/avito_parser`, `SYSTEMD_RESTART_UNITS=avito-web avito-worker avito-cleanup`, `WEBHOOK_LISTEN_PORT=9848`, `WEBHOOK_LISTEN_HOST=127.0.0.1`.

**10. systemd hook**

```bash
sudo cp /opt/avito_parser/deploy/avito-parser-github-hook.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now avito-parser-github-hook.service
sudo systemctl status avito-parser-github-hook.service --no-pager
curl -fsS http://127.0.0.1:9848/hooks/avito-parser/health
```

**11. Nginx на `:80`** — в активный `server { }` добавьте строку:

```nginx
include /etc/nginx/snippets/avito-parser-github-hook.conf;
```

Подготовка сниппета и reload:

```bash
sudo tee /etc/nginx/snippets/avito-parser-github-hook.conf >/dev/null </opt/avito_parser/deploy/nginx-avito-parser-github-hook.conf
sudo nginx -t && sudo systemctl reload nginx
```

**Порт 80 занят Apache** — вставьте строки из `deploy/apache-avito-parser-github-hook-snippet.conf.example` в нужный vhost **выше** общего `ProxyPass /`, затем `sudo apache2ctl configtest && sudo systemctl reload apache2`.

**Без правок веб-сервера** (как у `ai_parser`): в `/etc/avito-parser-deploy-hook.env` задайте `WEBHOOK_LISTEN_HOST=0.0.0.0`, откройте UFW `9848/tcp`, в GitHub URL: **`http://37.230.116.197:9848/hooks/avito-parser/`**, слушатель перезапустите: `sudo systemctl restart avito-parser-github-hook.service`.

**12. GitHub → Settings → Webhooks**

- Payload URL: `http://37.230.116.197/hooks/avito-parser/` (nginx/apache) **или** `http://37.230.116.197:9848/hooks/avito-parser/` (прямой порт)
- Content type: **application/json**, Secret из шага 9, события: **Just the push event**

**13. Запуск приложения и проверка**

```bash
sudo systemctl start avito-web avito-worker avito-cleanup
sudo systemctl status avito-web avito-worker avito-cleanup --no-pager
sudo tail -n 30 /var/log/avito-parser-redeploy.log
```

После пуша в `main` смотрите тот же лог и `sudo journalctl -u avito-parser-github-hook.service -n 30 --no-pager`.

## Логи и диагностика

### Лог-файл приложения
- `logs/app.log` (JSON)

### Логи systemd

```bash
sudo journalctl -u avito-web -f
sudo journalctl -u avito-worker -f
sudo journalctl -u avito-cleanup -f
```

## Эксплуатация

- Обработка идет строго последовательно: 1 строка -> 1 AI-запрос.
- При ошибке AI-ответа применяется retry по настройкам `.env`.
- Prompt редактируется отдельно: `prompts/parse_description.txt`.
- Загруженные и итоговые файлы удаляются по TTL, чтобы не засорять диск.

## Быстрый чек-лист

- Заполнен `.env` (`ROUTERAI_API_KEY` обязательно)
- Запущены `app.py`, `worker.py --mode worker`, `worker.py --mode cleanup`
- Открывается `/`, файл `.xlsx` загружается, прогресс обновляется, `Скачать` активируется после завершения
