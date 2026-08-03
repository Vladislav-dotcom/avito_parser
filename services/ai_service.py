from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any, List, Optional, Tuple

import httpx
from pydantic import BaseModel, ValidationError, field_validator

from config import Config
from services.price_service import sanitize_multi_item_prices, should_exclude_catalog_row
from services.prompt_service import load_prompt_template
from services.text_service import merge_parsed_items, split_description_chunks

logger = logging.getLogger(__name__)

_ALLOWED_CONDITIONS = {"новое", "бу", "без коробки"}
_CHUNK_PREFIX = (
    "Фрагмент {index} из {total} одного объявления. "
    "Извлеки позиции только из этого фрагмента, не додумывай данные из других частей.\n\n"
)


class ParsedDescription(BaseModel):
    brand: Optional[str] = None
    article: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[int] = None
    condition: Optional[str] = None
    generated_description: Optional[str] = None

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in _ALLOWED_CONDITIONS:
            return None
        return normalized

    @field_validator("generated_description")
    @classmethod
    def validate_generated_description(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        return normalized


def _extract_message_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices:
        raise ValueError("RouterAI вернул пустой список choices.")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if not isinstance(content, str):
        raise ValueError("RouterAI вернул некорректный тип content.")
    return content.strip()


def _normalize_list_payload(data: Any) -> List[dict[str, Any]]:
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        normalized_items: List[dict[str, Any]] = []
        for item in data:
            if isinstance(item, dict):
                normalized_items.append(item)
        if normalized_items:
            return normalized_items
        raise ValueError("RouterAI вернул массив без валидных объектов.")
    raise ValueError("RouterAI вернул JSON не в формате объекта или массива объектов.")


def _parse_json_response(content: str) -> List[ParsedDescription]:
    if content.startswith("```"):
        content = content.replace("```json", "").replace("```", "").strip()
    data = json.loads(content)
    items = _normalize_list_payload(data)
    parsed_items = [ParsedDescription.model_validate(item) for item in items]
    if not parsed_items:
        raise ValueError("RouterAI не вернул ни одной позиции.")
    return parsed_items


def _empty_result() -> List[dict[str, Any]]:
    return [ParsedDescription().model_dump()]


def _build_prompt_text(
    prompt_template: str,
    row_data: dict[str, Any],
    description: str,
    *,
    chunk_index: int | None = None,
    chunk_total: int | None = None,
) -> str:
    if chunk_index is not None and chunk_total is not None and chunk_total > 1:
        description = _CHUNK_PREFIX.format(index=chunk_index, total=chunk_total) + description

    return prompt_template.format(
        description=description,
        name=row_data.get("Наименование", ""),
        section=row_data.get("Раздел", ""),
        category=row_data.get("Категория", ""),
        price=row_data.get("Цена", ""),
        currency=row_data.get("Валюта", ""),
    )


def _request_parse(
    prompt_text: str,
    job_id: str,
) -> Tuple[List[dict[str, Any]], Optional[str]]:
    request_body = {
        "model": Config.ROUTERAI_MODEL,
        "messages": [
            {"role": "system", "content": "Ты извлекаешь структуру из текста и отвечаешь только JSON."},
            {"role": "user", "content": prompt_text},
        ],
        "temperature": 0,
    }

    api_url = f"{Config.ROUTERAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {Config.ROUTERAI_API_KEY}",
        "Content-Type": "application/json",
    }

    last_error = "unknown"
    for attempt in range(Config.AI_RETRIES + 1):
        started = time.perf_counter()
        try:
            with httpx.Client(timeout=Config.AI_REQUEST_TIMEOUT_SECONDS) as client:
                response = client.post(api_url, headers=headers, json=request_body)
                response.raise_for_status()
                content = _extract_message_content(response.json())
                parsed_items = _parse_json_response(content)

            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.info("AI запрос выполнен", extra={"job_id": job_id})
            logger.info(f"AI latency_ms={latency_ms}", extra={"job_id": job_id})
            return [item.model_dump() for item in parsed_items], None
        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, ValueError) as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            last_error = str(exc)
            logger.warning(
                f"Ошибка AI запроса, attempt={attempt + 1}, latency_ms={latency_ms}, reason={last_error}",
                extra={"job_id": job_id},
            )
            if attempt < Config.AI_RETRIES:
                time.sleep(Config.AI_RETRY_DELAY_SECONDS)

    return _empty_result(), last_error


def parse_description(
    description: str,
    row_data: dict[str, Any],
    job_id: str,
    *,
    row_price: Any = None,
    on_chunk_done: Callable[[], None] | None = None,
) -> Tuple[List[dict[str, Any]], Optional[str]]:
    prompt_template = load_prompt_template(Config.PROMPT_FILE)
    text = description or ""
    chunks = split_description_chunks(text, Config.AI_DESCRIPTION_CHUNK_CHARS)

    if len(chunks) > 1:
        logger.info(
            f"Описание разбито на {len(chunks)} фрагментов ({len(text)} символов)",
            extra={"job_id": job_id},
        )

    chunk_results: list[list[dict[str, Any]]] = []
    errors: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        prompt_text = _build_prompt_text(
            prompt_template,
            row_data,
            chunk,
            chunk_index=index,
            chunk_total=len(chunks),
        )
        parsed_items, error = _request_parse(prompt_text, job_id)
        chunk_results.append(parsed_items)
        if error:
            errors.append(error)

        if on_chunk_done is not None:
            on_chunk_done()

        merged_so_far = merge_parsed_items(chunk_results)
        sanitized = sanitize_multi_item_prices(merged_so_far, row_price)
        if should_exclude_catalog_row(sanitized) and index < len(chunks):
            logger.info(
                f"Пропуск остальных фрагментов: каталог без цен после chunk {index}/{len(chunks)}",
                extra={"job_id": job_id},
            )
            return sanitized, None

    merged = merge_parsed_items(chunk_results)
    if merged and merged != [{}]:
        if errors:
            logger.warning(
                f"Часть фрагментов описания с ошибкой: {'; '.join(errors)}",
                extra={"job_id": job_id},
            )
        return merged, None

    if errors:
        return _empty_result(), errors[-1]
    return merged, None
