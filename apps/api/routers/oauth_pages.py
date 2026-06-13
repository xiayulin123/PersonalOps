"""Browser OAuth redirect pages for web / cloud edition (Plan B B0)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["oauth-pages"])


def _oauth_result_html(provider: str, query: dict[str, str | None]) -> str:
    payload = {
        "provider": provider,
        "code": query.get("code"),
        "state": query.get("state"),
        "error": query.get("error"),
        "error_description": query.get("error_description"),
    }
    payload_json = json.dumps(payload)
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>PersonalOps</title></head>
<body style="font-family: system-ui, sans-serif; text-align: center; padding: 48px;">
  <h1>Sign-in complete</h1>
  <p>You can close this tab and return to PersonalOps.</p>
  <script>
    (function () {{
      var msg = {{ type: "personalops-oauth-callback", payload: {payload_json} }};
      if (window.opener) {{
        window.opener.postMessage(msg, "*");
      }}
      setTimeout(function () {{ window.close(); }}, 400);
    }})();
  </script>
</body>
</html>"""


@router.get("/oauth/microsoft/callback", response_class=HTMLResponse)
async def microsoft_oauth_page(request: Request) -> HTMLResponse:
    return HTMLResponse(_oauth_result_html("microsoft", dict(request.query_params)))


@router.get("/oauth/google/callback", response_class=HTMLResponse)
async def google_oauth_page(request: Request) -> HTMLResponse:
    return HTMLResponse(_oauth_result_html("google", dict(request.query_params)))
