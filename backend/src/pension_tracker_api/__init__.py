"""pensionTracker's backend: the Python code that runs inside AWS Lambda.

Each public module holds the handler for one area of the API (``health`` now;
pots, holdings, summary... later). Shared helpers, such as building HTTP
responses, live in their own modules so every handler behaves consistently.

How a request reaches this code (once deployed):

1. The browser calls ``https://<domain>/api/...``.
2. CloudFront routes ``/api/*`` to API Gateway's HTTP API.
3. API Gateway (after checking the sign-in token on protected routes) invokes
   the matching Lambda function, passing the request as an ``event`` dict.
4. The Lambda runtime calls the handler function in one of these modules, and
   whatever dict it returns becomes the HTTP response.
"""
