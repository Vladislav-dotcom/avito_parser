from __future__ import annotations

import json
import logging
import time
from typing import Any, List, Optional, Tuple

import httpx
from pydantic import BaseModel, ValidationError, field_validator

from config import Config
from services.prompt_service import load_prompt_template

logger = logging.getLogger(__name__)

_ALLOWED_CONDITIONS = {"новое", "бу", "без коробки"}


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


def parse_description(
    description: str,
    row_data: dict[str, Any],
    job_id: str,
) -> Tuple[List[dict[str, Any]], Optional[str]]:
    prompt_template = load_prompt_template(Config.PROMPT_FILE)
    prompt_text = prompt_template.format(
        description=description or "",
        name=row_data.get("Наименование", ""),
        section=row_data.get("Раздел", ""),
        category=row_data.get("Категория", ""),
        price=row_data.get("Цена", ""),
        currency=row_data.get("Валюта", ""),
    )

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
            logger.info(
                "AI запрос выполнен",
                extra={"job_id": job_id},
            )
            logger.info(
                f"AI latency_ms={latency_ms}",
                extra={"job_id": job_id},
            )
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
