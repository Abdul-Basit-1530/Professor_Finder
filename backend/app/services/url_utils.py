"""URL validation, normalisation and domain helpers (incl. SSRF guards)."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

# Second-level public suffixes common for universities. Good enough without
# shipping the full Public Suffix List.
_TWO_LEVEL_SUFFIXES = {
    "edu.cn", "ac.cn", "com.cn", "org.cn", "net.cn", "gov.cn",
    "edu.hk", "edu.tw", "edu.mo", "org.hk", "com.hk",
    "ac.uk", "co.uk", "edu.au", "ac.jp", "ac.kr", "edu.sg", "edu.my", "ac.nz",
}

_SKIP_SCHEMES = ("mailto:", "javascript:", "tel:", "data:", "#")
_BINARY_EXT = (
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".mp4", ".mp3",
    ".avi", ".mov", ".zip", ".rar", ".7z", ".exe", ".dmg", ".css", ".js", ".woff", ".woff2",
)


class InvalidURLError(ValueError):
    pass


def validate_university_url(url: str) -> str:
    """Validate a user-supplied URL and return its normalised form."""
    if not url or not url.strip():
        raise InvalidURLError("URL is required.")
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise InvalidURLError("Only http(s) URLs are supported.")
    host = (parts.hostname or "").lower()
    if not host or "." not in host:
        raise InvalidURLError("URL must contain a valid host name.")
    if host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
        raise InvalidURLError("Local/internal hosts are not allowed.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        raise InvalidURLError("Please provide the university's domain name, not an IP address.")
    if len(url) > 2048:
        raise InvalidURLError("URL is too long.")
    return normalize_url(url)


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower() or "https"
    host = (parts.hostname or "").lower()
    port = parts.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def canonical_key(url: str) -> str:
    """Key used for de-duplicating URLs (ignores scheme, www., trailing slash)."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower().removeprefix("www.")
    path = parts.path.rstrip("/") or "/"
    return f"{host}{path}?{parts.query}" if parts.query else f"{host}{path}"


def hostname(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def registrable_domain(url_or_host: str) -> str:
    host = hostname(url_or_host) if "://" in url_or_host else url_or_host.lower()
    labels = [lbl for lbl in host.split(".") if lbl]
    if len(labels) >= 3 and ".".join(labels[-2:]) in _TWO_LEVEL_SUFFIXES:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def is_official(url: str, domain: str) -> bool:
    host = hostname(url)
    return host == domain or host.endswith("." + domain)


def resolve_link(base: str, href: str | None) -> str | None:
    if not href:
        return None
    href = href.strip()
    if not href or href.lower().startswith(_SKIP_SCHEMES):
        return None
    try:
        absolute = urljoin(base, href)
    except ValueError:
        return None
    parts = urlsplit(absolute)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.path.lower().endswith(_BINARY_EXT):
        return None
    return normalize_url(absolute)


def is_pdf_url(url: str) -> bool:
    return urlsplit(url).path.lower().endswith(".pdf")


def host_is_public(host: str) -> bool:
    """Resolve `host` and ensure none of its addresses are private/loopback (SSRF guard)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True
