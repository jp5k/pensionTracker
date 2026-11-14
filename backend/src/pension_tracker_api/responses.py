"""Build HTTP responses in the shape API Gateway's HTTP API expects.

Why this module exists: a Lambda behind an HTTP API doesn't write to a socket
like a normal web server. It *returns a dict*, and API Gateway turns that dict
into the HTTP response. The dict must follow API Gateway's "payload format
version 2.0" response shape (``statusCode``, ``headers``, ``body``...). Getting
that shape slightly wrong (e.g. returning ``body`` as a dict instead of a
string) produces a confusing 500 error, so every handler builds its responses
here instead of hand-writing dicts.

See: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-lambda.html
"""

import json
from typing import Any, TypedDict


class ApiResponse(TypedDict):
    """The dict a Lambda returns to API Gateway (payload format version 2.0).

    A ``TypedDict`` is an ordinary dict at runtime, but it tells mypy exactly
    which keys exist and what type each holds. So a typo like ``statuscode``,
    or a non-string ``body``, is caught by the type checker before deployment
    instead of by a 500 error in production.

    Attributes:
        statusCode: The HTTP status code, e.g. 200 or 404.
        headers: HTTP response headers. Header *values* must be strings.
        body: The response body. API Gateway requires a **string**, so JSON
            must be serialized first (see ``json_response``).
        isBase64Encoded: Whether ``body`` is base64 (only for binary data such
            as images). Always ``False`` for our JSON API.
    """

    # These keys are camelCase because API Gateway defines them that way; the
    # N815 naming rule (mixedCase in class scope) is silenced for that reason.
    statusCode: int  # noqa: N815
    headers: dict[str, str]
    body: str
    isBase64Encoded: bool  # noqa: N815


def json_response(status_code: int, payload: dict[str, Any]) -> ApiResponse:
    """Return ``payload`` as a JSON HTTP response with the given status code.

    Args:
        status_code: HTTP status, e.g. 200 (OK), 400 (bad request), 404.
        payload: Any JSON-serializable dict to send back to the browser.

    Returns:
        A response dict API Gateway can turn directly into an HTTP response.

    Two headers are always set:

    * ``Content-Type: application/json`` so the browser (and ``fetch``) knows
      how to parse the body.
    * ``Cache-Control: no-store`` so neither the browser nor CloudFront ever
      caches API responses. API data is per-user and changes often; a cached
      response could show stale values or, worse, one user's data to another.
      (The ``/api/*`` CloudFront behaviour will also disable caching; this is a
      second, independent layer of the same protection.)
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Cache-Control": "no-store",
        },
        # json.dumps turns the dict into a string, which API Gateway requires.
        # separators=(",", ":") drops the spaces json.dumps adds by default,
        # making responses slightly smaller (no reader needs them pretty).
        "body": json.dumps(payload, separators=(",", ":")),
        "isBase64Encoded": False,
    }
