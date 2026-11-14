"""Tests for ``json_response``: every handler's responses depend on it being right."""

import json

from pension_tracker_api.responses import json_response


def test_body_is_a_json_string_not_a_dict() -> None:
    """API Gateway rejects a non-string ``body`` with a 500, so it must be serialized."""
    response = json_response(200, {"status": "ok", "count": 3})

    assert isinstance(response["body"], str)
    assert json.loads(response["body"]) == {"status": "ok", "count": 3}


def test_status_code_is_passed_through() -> None:
    """The caller's status code (here a 404) must reach the client unchanged."""
    assert json_response(404, {"error": "not found"})["statusCode"] == 404


def test_json_content_type_and_no_caching() -> None:
    """Browsers need the JSON content type; ``no-store`` stops any caching of per-user data."""
    headers = json_response(200, {})["headers"]

    assert headers["Content-Type"] == "application/json"
    assert headers["Cache-Control"] == "no-store"


def test_body_is_compact_and_not_base64() -> None:
    """No padding spaces in the JSON, and the body is plain text rather than base64 binary."""
    response = json_response(200, {"a": 1, "b": [1, 2]})

    assert response["body"] == '{"a":1,"b":[1,2]}'
    assert response["isBase64Encoded"] is False
