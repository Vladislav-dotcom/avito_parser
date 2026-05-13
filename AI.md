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

Добавляемые выходные колонки:
- `Бренд`
- `Артикул`
- `Цена`
- `Кол-во`
- `Состояние`
- `Описание` (AI-сгенерированное краткое техническое описание товара)

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
- В `templates/login.html` возле заголовка формы входа добавлена тестовая пометка `test`.

Конфиг:
- `AUTH_USERNAME`
- `AUTH_PASSWORD`
- `SECRET_KEY`

## Важные ограничения и инварианты

1. Вызовы к RouterAI только синхронные и по одной строке (без async/параллели).
2. Нельзя ломать контракт статусов job (`queued/processing/finished/failed`) — фронт на это опирается.
3. Нельзя удалять механизм TTL-очистки — иначе диск забьется файлами.
4. `job_id` хранится на фронте в `localStorage` для восстановления прогресса после reload.
5. Prompt должен оставаться во внешнем файле (`prompts/parse_description.txt`), не хардкодить в Python.
6. Выходное `Описание` в результирующем XLSX должно быть AI-сгенерированным, а не исходным полем из входного файла.
7. AI-описание формируется только для строк, прошедших основной AI-разбор и попавших в результат.

## Где что править

- API и auth: `app.py`
- Очередь/БД: `services/db_service.py`, `services/job_service.py`
- Пайплайн обработки: `tasks.py`
- Очистка файлов: `services/cleanup_service.py`, `worker.py --mode cleanup`
- AI парсинг и retry: `services/ai_service.py`
- UI/polling: `static/app.js`, `templates/index.html`, `templates/login.html`

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

Это не сбой агента в репозитории: GitHub **не получил HTTP-ответ** от Payload URL за отведённое время (порядка **10 с**). Обработчик `deploy/github_webhook_listener.py` сразу ставит деплой в фон и отдаёт **202** — при типичном таймауте проблема **до** приложения: сеть, firewall, nginx, юнит не слушает порт.

Проверить по приоритету:

1. На VPS: `systemctl status avito-parser-github-hook` — процесс жив, слушает `127.0.0.1:9848`.
2. `curl -sS -m 5 http://127.0.0.1:9848/health` с сервера — JSON `status: ok`.
3. С **внешней** машины (не с VPS): тот же URL, что в GitHub (**HTTPS/HTTP как в настройках**), например `curl -m 15 -v https://домен/hooks/avito-parser/` — должен быстро ответить (GET health, если путь совпадает с конфигом nginx).
4. Firewall / security group: **входящие** на 443 (или 80, если так настроено) не DROP без ответа — иначе клиент долго ждёт и таймаутится.
5. Nginx: `nginx -t`, лог ошибок upstream; при мёртвом бэкенде см. `proxy_connect_timeout` в `deploy/nginx-avito-parser-github-hook.conf`.

Повторная доставка с тем же результатом означает стабильную недоступность или зависание цепочки до ответа, а не разовый сбой GitHub.

## Быстрый smoke-check после правок

1. Логин в UI проходит.
2. Загрузка XLSX создает job.
3. Прогресс обновляется и восстанавливается после перезагрузки страницы.
4. После завершения активна кнопка `Скачать`.
5. Worker и cleanup живы, в логах нет критичных ошибок.
