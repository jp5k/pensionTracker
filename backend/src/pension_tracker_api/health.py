"""``GET /api/health``: a tiny endpoint that reports the API is up.

Why have a health endpoint at all?

* It's the simplest possible request through the whole chain (CloudFront →
  API Gateway → Lambda), so it's the first thing deployed: if it works, the
  wiring works, before any database or sign-in is involved.
* It's useful forever after: a quick ``curl`` (or, later, a monitoring check)
  confirms the API is reachable without needing a signed-in user.

It is deliberately **public** (no sign-in) and returns **nothing sensitive**:
no version numbers, environment details or configuration that could help an
attacker. Just "ok".

This module is written and tested now; it gets deployed in the "First Lambda
end-to-end" item of the plan.
"""

from typing import Any

from pension_tracker_api.responses import ApiResponse, json_response


def handler(event: dict[str, Any], context: Any) -> ApiResponse:
    """Lambda entry point: answer every request with HTTP 200 ``{"status": "ok"}``.

    Lambda calls this function once per request. The name ``handler`` is a
    convention; CDK will point the Lambda at ``pension_tracker_api.health.handler``.

    Args:
        event: The HTTP request, as a dict built by API Gateway (method, path,
            headers, query string...). Unused here: every request gets the same
            answer, but every handler must accept it.
        context: Runtime information from Lambda (request ID, time remaining
            before timeout...). Also unused here. Typed as ``Any`` because its
            real type (``LambdaContext``) comes from AWS Lambda Powertools,
            which isn't a dependency yet.

    Returns:
        A 200 JSON response, in API Gateway's expected format.
    """
    # Both parameters are intentionally ignored; `del` documents that and keeps
    # linters from flagging them as unused.
    del event, context
    return json_response(200, {"status": "ok"})
