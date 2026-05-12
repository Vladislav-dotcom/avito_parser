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
python -m pip install gunicorn
```

Создай `.env` в `/opt/avito_parser/.env` и укажи реальный `ROUTERAI_API_KEY`.

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
