"""Unit tests for SSRF protection (app/url_safety.py)."""
import pytest

from app.url_safety import UnsafeTargetError, validate_target_url
from tests.conftest import fake_resolver

INTERNAL = ["postgres", "target-service"]


def check(url: str, allow_private: bool = True) -> None:
    validate_target_url(url, blocked_hosts=INTERNAL, allow_private=allow_private, resolver=fake_resolver)


@pytest.mark.parametrize(
    "url",
    [
        "http://demo-app/",  # Docker Compose app on a private address
        "https://example.com/health",
        "http://93.184.216.34:8080/status",
    ],
)
def test_allowed_urls(url):
    check(url)


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("ftp://example.com/", "Only http and https"),
        ("http://user:secret@example.com/", "embedded credentials"),
        ("http://localhost:8000/", "internal"),
        ("http://LOCALHOST./", "internal"),
        ("http://api.localhost/", "internal"),
        ("http://metadata.google.internal/", "internal"),
        ("http://host.docker.internal/", "internal"),
        ("http://postgres:5432/", "internal"),  # configured MiniOps host
        ("http://127.0.0.1/", "loopback"),
        ("http://127.1.2.3/", "loopback"),
        ("http://[::1]/", "loopback"),
        ("http://[::ffff:127.0.0.1]/", "loopback"),  # IPv4-mapped IPv6
        ("http://169.254.169.254/latest/meta-data/", "link-local"),  # cloud metadata
        ("http://0.0.0.0/", "unspecified"),
        ("http://224.0.0.1/", "multicast"),
        ("http://240.0.0.1/", "reserved"),
        ("http://sneaky.example/", "loopback"),  # public-looking name, loopback answer
        ("http://metadata-alias.example/", "link-local"),
        ("http://172.18.0.2/", "internal MiniOps service"),  # postgres by IP instead of name
        ("http://no-such-host.example/", "could not be resolved"),
    ],
)
def test_blocked_urls(url, reason):
    with pytest.raises(UnsafeTargetError, match=reason):
        check(url)


def test_private_networks_can_be_disallowed():
    with pytest.raises(UnsafeTargetError, match="private-network"):
        check("http://demo-app/", allow_private=False)
    with pytest.raises(UnsafeTargetError, match="private-network"):
        check("http://192.168.1.10/", allow_private=False)


def test_every_resolved_address_is_checked():
    check("http://mixed.example/")  # public + private, private allowed
    with pytest.raises(UnsafeTargetError, match="private-network"):
        check("http://mixed.example/", allow_private=False)
