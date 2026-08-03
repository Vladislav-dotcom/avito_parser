from unittest.mock import patch

from services.ai_service import parse_description


def test_parse_description_skips_remaining_chunks_for_catalog(monkeypatch):
    monkeypatch.setattr(
        "services.ai_service.split_description_chunks",
        lambda text, max_chars: ["chunk-1", "chunk-2", "chunk-3"],
    )
    monkeypatch.setattr(
        "services.ai_service.load_prompt_template",
        lambda _path: "{description}|{name}|{section}|{category}|{price}|{currency}",
    )

    calls = {"count": 0}

    def fake_request(prompt_text, job_id):
        calls["count"] += 1
        return (
            [
                {"article": "A1", "price": None, "brand": None, "quantity": None, "condition": None, "generated_description": None},
                {"article": "B2", "price": None, "brand": None, "quantity": None, "condition": None, "generated_description": None},
            ],
            None,
        )

    heartbeats = {"count": 0}

    with patch("services.ai_service._request_parse", side_effect=fake_request):
        items, error = parse_description(
            description="long text",
            row_data={"Наименование": "x", "Раздел": "", "Категория": "", "Цена": 100, "Валюта": "RUB"},
            job_id="job-1",
            row_price=100,
            on_chunk_done=lambda: heartbeats.__setitem__("count", heartbeats["count"] + 1),
        )

    assert error is None
    assert calls["count"] == 1
    assert heartbeats["count"] == 1
    assert len(items) == 2
