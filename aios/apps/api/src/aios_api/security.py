"""セキュリティヘッダ付与(多層防御、NFR-SE / ペンテスト指摘の常套対策)。

制御プレーンは JSON API(ブラウザで直接描画しない)であるため、
CSP は最も厳格な `default-src 'none'` とし、クリックジャッキング・MIME
スニッフィング・リファラ漏洩・混在コンテンツを既定で塞ぐ。
HSTS は HTTPS 終端(Ingress/LB)前提で常時付与する。
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """全レスポンス(エラー含む)にセキュリティヘッダを付与する。"""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response
