# AI.md — контекст проекта

## Репозиторий (GitHub)

- URL: https://github.com/Vladislav-dotcom/avito_parser
- Ветка по умолчанию: `main`
- Локально: отдельный git в каталоге `avito_parser` (не путать с монорепо `D:/SERVERS/OLNISA`).

## Что это за сервис

`avito_parser` — веб-сервис для AI-обработки XLSX-файлов с данными по товарам (Avito-парсинг).

Цель:
- загрузить входной XLSX;
- для каждой строки проанализировать поле `Описание` через RouterAI;
- добавить структурированные колонки;
- дать пользователю скачать готовый XLSX.

## Зачем нужен

Ручной разбор `Описание` занимает много времени и часто неструктурирован.
Сервис автоматизирует это и приводит данные к единому виду.

## Вход/выход данных

Обязательные входные колонки:
- `Наименование`
- `Цена`
- `Валюта`
- `Кол-во в наличии`
- `Раздел`
- `Категория`
- `Описание`

Добавляемые выходные колонки (после AI, до финального экспорта):
- `Бренд`
- `Артикул`
- `Цена`
- `Кол-во`
- `Состояние` — базовое значение AI (`новое` / `бу` / `без коробки`) + автоматические маркеры из исходного `Описание` (`демонтаж`, `были смонтированы`, `в работе не было`), через запятую
- `Описание` (AI-сгенерированное краткое техническое описание товара)

### Фильтрация «каталожных» объявлений

- При **2+ артикулах** в одной строке цена каждой позиции берётся **только из текста описания** (промпт + safety-net в `services/price_service.py`).
- Если AI скопировал одну цену Avito на все позиции — цены обнуляются.
- Если **2+ артикула и ни у одного нет цены** — объявление целиком исключается из результата (0 строк).
- Одиночные объявления (1 артикул) не фильтруются.

### Экспорт под 1С (единственный формат результата)

- Финальный XLSX (`format_export_for_1c` в `services/excel_service.py`):
  - переименование: `Наименование`→`название`, `Бренд`→`производитель`, `Артикул`→`артикул`;
  - остальные колонки без изменений (все входные + AI-поля).

## Текущая архитектура (важно)

Сервис работает **без Redis**.

- Web/API: `Flask` (`app.py`)
- Очередь и статусы задач: `SQLite` (`storage/jobs.db`)
- Worker: `python worker.py --mode worker`
- Cleanup-процесс: `python worker.py --mode cleanup`
- AI-интеграция: RouterAI через sync `httpx` (`services/ai_service.py`)
- Prompt хранится отдельно: `prompts/parse_description.txt`

Поток:
1. Пользователь загружает файл (`/api/upload`)
2. Job создается в SQLite со state `queued`
3. Worker берет job, обрабатывает строки последовательно
4. Прогресс записывается в SQLite
5. Готовый файл сохраняется в `storage/results`
6. Пользователь скачивает по `/api/download/<job_id>`
7. Cleanup удаляет файлы по TTL

## Авторизация

Добавлена простая сессионная авторизация:
- `/login` (форма логин/пароль)
- `/logout`
- без авторизации API и UI закрыты

Конфиг:
- `AUTH_USERNAME`
- `AUTH_PASSWORD`
- `SECRET_KEY`

## Важные ограничения и инварианты

1. Вызовы к RouterAI только синхронные и по одной строке (без async/параллели).
2. Нельзя ломать контракт статусов job (`queued/processing/finished/failed`) — фронт на это опирается.
3. Нельзя удалять механизм TTL-очистки — иначе диск забьется файлами.
4. `job_id` хранится на фронте в `localStorage` и в URL (`?job_id=...`) для восстановления прогресса после reload.
5. Prompt должен оставаться во внешнем файле (`prompts/parse_description.txt`), не хардкодить в Python.
6. Выходное `Описание` в результирующем XLSX должно быть AI-сгенерированным, а не исходным полем из входного файла.
7. AI-описание формируется только для строк, прошедших основной AI-разбор и попавших в результат.

## Где что править

- API и auth: `app.py`
- Очередь/БД: `services/db_service.py`, `services/job_service.py`
- Пайплайн обработки: `tasks.py`, checkpoint: `services/checkpoint_service.py`
- Формат 1С в Excel: `services/excel_service.py` (`format_export_for_1c`)
- Очистка файлов: `services/cleanup_service.py`, `worker.py --mode cleanup`
- AI парсинг и retry: `services/ai_service.py`
- Нарезка длинных описаний / merge позиций: `services/text_service.py`
- Маркеры состояния из описания: `services/condition_service.py`
- Фильтр цен multi-item / каталоги: `services/price_service.py`
- Prompt: `prompts/parse_description.txt`

## Риски при изменениях

- Изменение формата ответа AI без адаптации парсера => рост `failed_rows`.
- Удаление/изменение колонок без миграции Excel-логики => падения при валидации.
- Удаление `before_request` auth-проверки => открытый доступ к сервису.
- Слишком маленький `FILE_TTL_SECONDS` => пользователь может не успеть скачать результат.

## Автодеплой (GitHub → VPS)

- Каталог в репо: `deploy/` (`redeploy.sh`, `github_webhook_listener.py`, обёртка с `flock`, systemd unit, nginx-сниппет).
- На одном VPS с `ai_parser`: **порт webhook 9848**, путь **`/hooks/avito-parser/`** (у `ai_parser` — 9847 и `/hooks/ai-parser/`).
- Env на сервере: `/etc/avito-parser-deploy-hook.env` (не в git). Юнит: `avito-parser-github-hook.service`.
- Рестарт после pull: `avito-web`, `avito-worker`, `avito-cleanup` (задаётся `SYSTEMD_RESTART_UNITS`).
- Пошаговые SSH-команды: раздел **«Автодеплой по push»** в `README.md`.

### Если в GitHub: «We couldn't deliver this payload: timed out»

Это не сбой агента в репозитории: GitHub **не получил HTTP-ответ** за ~10 с. Обработчик сразу ставит деплой в фон и отдаёт **202** — если ответа нет, ищи обрыв сети/nginx **или** зависший однопоточный приём (см. ниже), а не «медленный» сам деплой в том же HTTP-запросе.

Проверить по приоритету:

1. На VPS: `systemctl status avito-parser-github-hook` — процесс жив; порт смотри в env (`WEBHOOK_LISTEN_HOST`: часто `127.0.0.1`, у тебя может быть `0.0.0.0:9848`).
2. `curl -sS -m 5 http://127.0.0.1:9848/health` с сервера — JSON `status: ok`. На **9848 только HTTP**, не TLS: `https://...:9848` даст зависание на рукопожатии — проверяй `http://`.
3. С **внешней** машины: тот же URL, что в GitHub. Если `https://IP:443` → `connection refused`, nginx на 443 не слушает — либо подними прокси, либо вебхук на **http://** по схеме из `deploy/nginx-avito-parser-github-hook.conf` (там пример с `http://37.230.116.197/...`).
4. Firewall: входящие не DROP без ответа.
5. Nginx: `nginx -t`, лог upstream; таймауты в `deploy/nginx-avito-parser-github-hook.conf`.

Если `systemctl` показывает `running`, а `curl http://127.0.0.1:9848/health` **всё равно** таймаутится долгое время — типичная причина: старый однопоточный `HTTPServer` занят одним «зависшим» соединением (неполный POST и т.п.), остальные запросы не обрабатываются. В репо слушатель переведён на `ThreadingHTTPServer`; после деплоя при зависании достаточно `systemctl restart avito-parser-github-hook`.

Повторная доставка с тем же результатом означает стабильную недоступность или зависание цепочки до ответа, а не разовый сбой GitHub.

## Инструменты агента (CLI, глобальные)

### markitdown — конвертация файлов в Markdown

- **Установка**: `markitdown` + `markitdown-mcp` из `D:\PROGRAMS\markitdown` (editable install)
- **cli-use alias**: `markitdown` (зарегистрирован глобально)
- **Использование** (token-efficient, ~60–80% дешевле MCP):
  ```bash
  cli-use markitdown convert_to_markdown --uri "file:///D:/path/to/file.xlsx"
  ```
- **Прямой CLI** (ещё проще):
  ```bash
  markitdown "D:\path\to\file.xlsx"
  ```
- **Форматы**: xlsx, xls, pdf, docx, pptx, csv, json, xml, html, zip, изображения, YouTube URL
- **SKILL.md**: `~/.agents/skills/markitdown/SKILL.md` — глобальный, Cursor подхватывает автоматически
- **Важно для путей Windows**: `D:\папка\файл.xlsx` → URI `file:///D:/папка/файл.xlsx`

### cli-use (глобальный враппер MCP→CLI)

- **Установка**: `D:\PROGRAMS\cli_use\cli-use` (editable install), версия 0.3.0
- **Зарегистрированные aliases**: `fs`, `gh`, `memory`, `puppeteer`, `brave`, `slack`, `markitdown`
- **Конфиг aliases**: `C:\Users\wayks\.cli-use\aliases.json`
- **Смысл**: превращает MCP-сервер в CLI-команду, экономя 60–80% токенов на schema discovery и JSON-RPC overhead

## Cursor Skills (глобальные, пользователю)

- Менеджер: `npx skills` (CLI `vercel-labs/skills`).
- Установленный skill: **frontend-design** (от `anthropics/skills`) — генерация качественных production-frontend UI (HTML/CSS, React и т.п.).
- Локация: `~/.agents/skills/frontend-design/SKILL.md` (Cursor IDE подхватывает её как user-level skill автоматически — см. [docs](https://cursor.com/docs/context/skills)).
- Установка: `npx skills add https://github.com/anthropics/skills --skill frontend-design -g -y`.
- Просмотр в IDE: Settings → Rules → раздел *Agent Decides*. Ручной вызов в чате: `/frontend-design`.
- **RouterAI API** (интеграция/доки RouterAI): глобальный skill `~/.agents/skills/routerai-api/SKILL.md` + `reference.md` (как остальные user-level skills); в чате подключать явно (`@routerai-api` / выбор skill), `disable-model-invocation: true` — не подхватывается без явного указания пользователя на RouterAI.

## Связанный инструмент excel_editor

Каталоги radioelementy («Папка бренда», «Название производителя») чистятся отдельным CLI в `../excel_editor/`:
- полный прогон: `clean_excel.py`
- только бренды в готовом XLSX: `clean_brands_only.py` (без повторного AI)

## Зависший прогресс / стабильность worker

- Worker на старте сразу возвращает в `queued` все orphan `processing`/`finalizing` (`requeue_orphan_jobs`).
- Worker периодически вызывает `requeue_stale_processing_jobs` (интервал `STALE_REQUEUE_INTERVAL_SECONDS`, порог `STALE_PROGRESS_SECONDS` по `last_progress_at`); то же делает cleanup-loop.
- Watchdog-поток: если текущий job без прогресса дольше порога — `release_job_to_queue` + `os._exit(1)` (systemd `Restart=always`).
- При SIGTERM worker завершает текущую строку и возвращает job в `queued` (`release_job_to_queue`); redeploy делает `systemctl stop` для worker (см. `deploy/redeploy.sh`, `deploy/avito-worker.service`).
- `started_at` при requeue/resume **не сбрасывается** (`COALESCE` в claim) — иначе ETA после деплоя становится «~1 мин».
- Checkpoint в `storage/checkpoints/{job_id}.jsonl` — resume с места обрыва без повторного AI.
- Длинные `Описание` режутся на chunks (`AI_DESCRIPTION_CHUNK_CHARS`); после chunk mid-row heartbeat (`touch_job_progress`); если уже каталог без цен — остальные chunks не вызываются.
- API `/api/status` отдаёт `stale_warning`, `eta_seconds`, `rows_per_minute`, `elapsed_seconds`; ETA через `compute_progress_eta` (fallback на `created_at`, если скорость >1 строки/сек — типичный артефакт reset `started_at`).
- Прямая ссылка на job: `/?job_id=<uuid>`.
- Сервис не ходит на Avito и не делает веб-поиск: только RouterAI `chat/completions` по тексту из XLSX.

## Быстрый smoke-check после правок

1. Логин в UI проходит.
2. Загрузка XLSX создает job.
3. Прогресс обновляется (с ETA) и восстанавливается после перезагрузки страницы.
4. После завершения активна кнопка `Скачать`.
5. Worker и cleanup живы, в логах нет критичных ошибок.
