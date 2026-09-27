import pytest
from pydantic import ValidationError

from app import netguard
from app.netguard import BlockedUrlError, check_public_url
from app.schemas import IcsSourceCreate


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/cal.ics",
        "http://localhost:8080/cal.ics",
        "http://10.0.0.5/cal.ics",
        "http://192.168.1.10/dav/",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata endpoint
        "http://[::1]/cal.ics",
        "http://[::ffff:127.0.0.1]/cal.ics",
        "http://100.64.0.1/cal.ics",  # carrier-grade NAT, not public either
    ],
)
def test_check_public_url_blocks_non_public_addresses(url):
    with pytest.raises(BlockedUrlError):
        check_public_url(url)


def test_check_public_url_allows_public_address():
    check_public_url("https://1.1.1.1/cal.ics")


def test_check_public_url_allows_private_when_configured(monkeypatch):
    monkeypatch.setattr(netguard.settings, "allow_private_feed_urls", True)
    check_public_url("http://192.168.1.10/dav/")


def test_check_public_url_lets_unresolvable_hosts_through(monkeypatch):
    """The fetch fails on its own; a DNS hiccup at save time shouldn't make a URL unsaveable."""

    def no_dns(host, port):
        raise netguard.socket.gaierror("no DNS")

    monkeypatch.setattr(netguard.socket, "getaddrinfo", no_dns)
    check_public_url("https://calendar.example.com/cal.ics")


def test_ics_source_schema_rejects_private_url():
    with pytest.raises(ValidationError, match="non-public address"):
        IcsSourceCreate(url_or_path="http://127.0.0.1/cal.ics", offsets_minutes=[15])


def test_fetch_ics_text_refuses_redirect_into_private_network(monkeypatch):
    import httpx

    from app.scheduler import ics

    monkeypatch.setattr(
        netguard.socket,
        "getaddrinfo",
        lambda host, port: [(0, 0, 0, "", ("93.184.215.14" if host == "public.test" else "10.0.0.5", 0))],
    )

    def handler(request):
        if request.url.host == "public.test":
            return httpx.Response(302, headers={"Location": "http://internal.test/secret"})
        return httpx.Response(200, text="BEGIN:VCALENDAR\nEND:VCALENDAR")

    real_client = httpx.Client
    monkeypatch.setattr(ics.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs))

    with pytest.raises(BlockedUrlError):
        ics.fetch_ics_text("http://public.test/cal.ics")
