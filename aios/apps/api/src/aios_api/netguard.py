"""Webhook 送信先の SSRF ガード(API7、脅威モデル §5-2)。

Webhook URL 登録時に検証し、内部ネットワーク(ループバック・プライベート・
リンクローカル・予約)への送信を既定で遮断する。任意で許可ホストリストを
強制できる(AIOS_WEBHOOK_ALLOWED_HOSTS、サフィックス一致)。

- 既定スキームは https のみ。AIOS_WEBHOOK_ALLOW_HTTP=1 で http も許可(開発用)。
- ホストが IP リテラルなら直接判定、名前なら resolver で解決した全 IP を判定。
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Callable
from urllib.parse import urlparse

from aios_common.errors import InvalidWebhookUrlError

# (host) -> list of resolved IP 文字列。テストで差し替え可能。
Resolver = Callable[[str], list[str]]


def _default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


def _is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def _allowed_hosts_from_env() -> frozenset[str]:
    raw = os.environ.get("AIOS_WEBHOOK_ALLOWED_HOSTS", "")
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def validate_webhook_url(
    url: str,
    *,
    allow_http: bool | None = None,
    allowed_hosts: frozenset[str] | None = None,
    resolver: Resolver = _default_resolver,
) -> None:
    """不適格なら InvalidWebhookUrlError を送出。適格なら None。"""
    if allow_http is None:
        allow_http = os.environ.get("AIOS_WEBHOOK_ALLOW_HTTP") == "1"
    if allowed_hosts is None:
        allowed_hosts = _allowed_hosts_from_env()

    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if scheme not in allowed_schemes:
        raise InvalidWebhookUrlError(f"scheme {scheme!r} not allowed (need {allowed_schemes})")

    host = parsed.hostname
    if not host:
        raise InvalidWebhookUrlError("missing host")

    if allowed_hosts and not _host_in_allowlist(host.lower(), allowed_hosts):
        raise InvalidWebhookUrlError(f"host {host!r} not in allowlist")

    # IP リテラルか名前解決かを判定して全 IP を検査。
    # 高価値ベクタ(IP リテラルの内部アドレス、名前解決で内部 IP になるもの=
    # クラウドメタデータ 169.254.169.254 / ループバック / RFC1918 等)は確定的に遮断する。
    # 名前解決に失敗したホストは内部と証明できないため許可する(§5-2 の残存事項として
    # 明記。実運用ではエグレス制御と併用する)。
    try:
        ipaddress.ip_address(host)
        ips: list[str] = [host]
    except ValueError:
        try:
            ips = resolver(host)
        except OSError:
            return  # 解決不能は判定不能 → 許可(egress 制御で補完)

    for ip in ips:
        if _is_blocked_ip(ip):
            raise InvalidWebhookUrlError(
                f"host {host!r} resolves to non-public address {ip}"
            )


def _host_in_allowlist(host: str, allowed: frozenset[str]) -> bool:
    return any(host == a or host.endswith("." + a) for a in allowed)
