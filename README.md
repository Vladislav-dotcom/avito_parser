# AI-анализатор парсинга с Avito

## Доступ к VPS

Новый сервер: `206.223.249.181`, пользователь SSH: `avitoops`, ключ: `C:/Users/user/.ssh/avito_parser_206_223_249_181`. В локальном SSH-конфиге настроен алиас `avito-parser-new`:

```powershell
ssh avito-parser-new
```

**Никогда не подключайтесь к этому серверу по SSH как `root`.** Парольный SSH-вход для всех пользователей и SSH-вход `root` по ключу отключены. Административные действия выполняются через `sudo` из сессии `avitoops`.

Сервис открывается по [HTTP-адресу](http://206.223.249.181/login). HTTPS по IP в текущей конфигурации не настроен.

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

### Поставщик и формат 1С

- Перед анализом выберите **поставщика** в UI (один файл = один поставщик).
- Список поставщиков хранится в SQLite; стартовые: Еремеев, Неботов, Усмамбаев, Сергей, plc:Store.
- В UI можно добавить нового поставщика (только имя).
- Скачиваемый XLSX всегда в формате для 1С:
  - `название`, `производитель`, `артикул` (без суффиксов к артикулу).

### Какие колонки в выходном XLSX

Все входные колонки + AI-поля (`производитель`, `артикул`, `Цена`, `Кол-во`, `Состояние`, `Описание` и др.).

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
AI_DESCRIPTION_CHUNK_CHARS=5000
AI_RETRIES=2
AI_RETRY_DELAY_SECONDS=1.5
JOB_POLL_INTERVAL_SECONDS=1.0
STALE_PROGRESS_SECONDS=300
STALE_REQUEUE_INTERVAL_SECONDS=30
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

## Продакшн и автодеплой

Текущий VPS: `206.223.249.181`. Для SSH используйте только `avitoops` и ключ `C:/Users/user/.ssh/avito_parser_206_223_249_181` (`ssh avito-parser-new`). **Не подключайтесь как `root`**. Для административных действий внутри сессии используйте `sudo`. Парольный SSH-вход и SSH-вход `root` отключены.

- Код: `/opt/avito_parser`, ветка `main` репозитория `Vladislav-dotcom/avito_parser`.
- Веб: `avito-web` (Gunicorn на `127.0.0.1:8000`) через nginx на `http://206.223.249.181/`.
- Очередь: `avito-worker`; очистка по TTL: `avito-cleanup`.
- Данные: `/opt/avito_parser/storage`, SQLite: `storage/jobs.db`; секреты: `/opt/avito_parser/.env` (не в git).
- Вебхук: `avito-parser-github-hook` на `127.0.0.1:9848`, снаружи `http://206.223.249.181/hooks/avito-parser/`. GitHub webhook принимает push в `main` и запускает `deploy/redeploy.sh`.
- Конфигурация webhook: `/etc/avito-parser-deploy-hook.env` (не в git), шаблон: `deploy/avito-parser-deploy-hook.env.example`.
- Конфигурация nginx: `deploy/nginx-avito-parser-site.conf`; юниты: `deploy/avito-web.service`, `deploy/avito-worker.service`, `deploy/avito-cleanup.service`, `deploy/avito-parser-github-hook.service`.

Проверка служб и вебхука:

```bash
ssh avito-parser-new
sudo systemctl status avito-web avito-worker avito-cleanup avito-parser-github-hook nginx --no-pager
curl -fsS http://127.0.0.1:9848/hooks/avito-parser/health
sudo sqlite3 /opt/avito_parser/storage/jobs.db 'pragma integrity_check;'
```

Для ручного редеплоя подключитесь как `avitoops` и выполните `sudo bash /opt/avito_parser/deploy/avito-parser-redeploy-wrapper.sh`. Прямой SSH-вход `root` для этого не нужен.

Сервис доступен по IP, доменного имени у него нет. Старый IP после переноса не должен обслуживать приложение.

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
