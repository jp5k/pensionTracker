"""Tests for the ``GET /api/health`` handler."""

import json
from typing import Any

from pension_tracker_api.health import handler

#: A trimmed-down example of the event API Gateway sends for ``GET /api/health``
#: (payload format version 2.0). Real events carry many more fields; the
#: handler ignores the event entirely, but using a realistic one keeps the test
#: honest about what Lambda will actually pass in.
HEALTH_EVENT: dict[str, Any] = {
    "version": "2.0",
    "routeKey": "GET /api/health",
    "rawPath": "/api/health",
    "headers": {"accept": "application/json"},
    "requestContext": {"http": {"method": "GET", "path": "/api/health"}},
}


def test_health_returns_200_ok() -> None:
    """The endpoint's whole job: answer 200 with ``{"status": "ok"}``."""
    response = handler(HEALTH_EVENT, None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"status": "ok"}


def test_health_reveals_nothing_else() -> None:
    """It's public, so it must not leak versions or config that could help an attacker."""
    body = json.loads(handler(HEALTH_EVENT, None)["body"])

    assert set(body) == {"status"}
