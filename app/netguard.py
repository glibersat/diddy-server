"""Refuses server-side fetches of user-supplied URLs (ICS feeds, CalDAV lists) that point into
the server's own network - see app/config.py::allow_private_feed_urls.

Checked both when a URL is saved (app/schemas.py, for an immediate 422) and on every request
the fetchers make, redirect hops included (app/scheduler/ics.py, app/scheduler/todo.py), since
a public URL can redirect inward and DNS can change after the URL was saved. The check resolves
the hostname itself, so a DNS answer that changes between this check and the actual connect
isn't caught - good enough to stop casual probing, not a hard sandbox."""

import ipaddress
import socket
from urllib.parse import urlsplit

from app.config import settings


class BlockedUrlError(ValueError):
    pass


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop an IPv6 zone id ("fe80::1%eth0")
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_public_url(url: str) -> None:
    """Raise BlockedUrlError if `url`'s host resolves to any non-public address. A host that
    doesn't resolve at all passes - the fetch itself will fail on it, and a DNS hiccup while
    saving a URL shouldn't make it unsaveable."""
    if settings.allow_private_feed_urls:
        return
    host = urlsplit(url).hostname
    if not host:
        raise BlockedUrlError(f"URL has no host: {url!r}")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return
    for *_, sockaddr in infos:
        address = str(sockaddr[0])
        if not _is_public(address):
            raise BlockedUrlError(
                f"{host} resolves to non-public address {address} "
                "(set DIDDY_ALLOW_PRIVATE_FEED_URLS=true to allow LAN feeds)"
            )
