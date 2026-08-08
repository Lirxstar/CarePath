from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class _RejectRedirects(HTTPRedirectHandler):
    """Refuse redirects so a trusted loopback endpoint cannot bounce data off-host."""

    def redirect_request(
        self,
        req: Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def open_loopback(request: Request, timeout: float) -> Any:
    """Open one request without environment proxies or HTTP redirects."""

    opener = build_opener(ProxyHandler({}), _RejectRedirects())
    return opener.open(request, timeout=timeout)


def assert_loopback_resolution(base_url: str) -> None:
    """Require every resolved address for a configured local endpoint to stay loopback-only."""

    parsed = urlparse(base_url)
    hostname = parsed.hostname
    if hostname is None:
        raise ValueError("local LLM base URL must include a loopback hostname")
    port = parsed.port or 80
    try:
        addresses = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("local LLM loopback hostname could not be resolved") from exc
    if not addresses:
        raise ValueError("local LLM loopback hostname did not resolve")
    for address in addresses:
        raw_address = str(address[4][0]).split("%", 1)[0]
        try:
            parsed_address = ipaddress.ip_address(raw_address)
        except ValueError as exc:
            raise ValueError("local LLM base URL resolved to an invalid IP address") from exc
        if not parsed_address.is_loopback:
            raise ValueError("local LLM hostname must resolve only to loopback addresses")
