import pytest
from pydantic import ValidationError

from services.ai_service import _parse_json_response


def test_parse_json_response_success():
    payload = '{"brand":"ABB","article":"A1","price":100.5,"quantity":2,"condition":"бу","generated_description":"Краткое описание"}'
    result = _parse_json_response(payload)
    assert result[0].brand == "ABB"
    assert result[0].condition == "бу"
    assert result[0].generated_description == "Краткое описание"


def test_parse_json_response_success_with_array():
    payload = '[{"brand":"ABB","article":"A1","price":100.5,"quantity":2,"condition":"бу","generated_description":"Описание"}]'
    result = _parse_json_response(payload)
    assert result[0].brand == "ABB"
    assert result[0].condition == "бу"
    assert result[0].generated_description == "Описание"


def test_parse_json_response_success_with_multi_items():
    payload = '[{"brand":"ABB","article":"A1","price":100.5,"quantity":2,"condition":"бу","generated_description":"Описание 1"},{"brand":"IFM","article":"B2","price":200,"quantity":1,"condition":"новое","generated_description":"Описание 2"}]'
    result = _parse_json_response(payload)
    assert len(result) == 2
    assert result[1].article == "B2"
    assert result[1].generated_description == "Описание 2"


def test_parse_json_response_generated_description_empty_to_none():
    payload = '{"brand":"ABB","article":"A1","price":100.5,"quantity":2,"condition":"бу","generated_description":"   "}'
    result = _parse_json_response(payload)
    assert result[0].generated_description is None


def test_parse_json_response_invalid_json():
    with pytest.raises(ValueError):
        _parse_json_response("not-json")


def test_parse_json_response_invalid_schema():
    with pytest.raises(ValidationError):
        _parse_json_response('{"brand":"A","quantity":"many"}')
