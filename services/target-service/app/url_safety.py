"""SSRF protection for monitoring targets (docs/MiniCloudOps.md §16, "Monitoring safety").

The Monitoring Service will send requests to whatever URL is registered here, so a target must
never point at something only the platform itself can reach. A URL is rejected when:

* its scheme is not http/https, or it embeds credentials (user:pass@host);
* its host is a known internal name (localhost, cloud metadata, MiniOps's own containers);
* its host resolves to a loopback, link-local (includes 169.254.169.254 cloud metadata),
  unspecified, multicast or reserved address;
* its host resolves to the same IP as one of the blocked internal names, which stops someone
  registering "postgres" by its container IP instead of its name;
* private-network addresses are disallowed by configuration and the host resolves to one.

Private ranges are allowed by default because in Docker Compose every monitored application has
one (172.x). Set SSRF_ALLOW_PRIVATE_NETWORKS=false when targets are public services only.

Every resolved address is checked, not just the first. The Monitoring Service re-checks before
each request, which also covers DNS answers that change after registration.
"""
import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

Resolver = Callable[[str, int], list[str]]
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address

ALWAYS_BLOCKED_HOSTS = frozenset(
    {"localhost", "metadata", "metadata.google.internal", "host.docker.internal", "gateway.docker.internal"}
)


class UnsafeTargetError(ValueError):
    """The URL must not be monitored. The message is safe to return to the client."""


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({info[4][0] for info in infos})


def _parse_ip(value: str) -> IPAddress:
    ip = ipaddress.ip_address(value.split("%", 1)[0])  # drop an IPv6 zone id like fe80::1%eth0
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return ip.ipv4_mapped  # ::ffff:127.0.0.1 is really 127.0.0.1
    return ip


def _address_problem(ip: IPAddress, allow_private: bool) -> str | None:
    if ip.is_loopback:
        return "loopback"
    if ip.is_link_local:
        return "link-local"
    if ip.is_unspecified:
        return "unspecified"
    if ip.is_multicast:
        return "multicast"
    if ip.is_reserved:
        return "reserved"
    if ip.is_private and not allow_private:
        return "private-network"
    return None


def _resolve(host: str, port: int, resolver: Resolver) -> list[IPAddress]:
    try:
        return [_parse_ip(addr) for addr in resolver(host, port)]
    except (OSError, UnicodeError, ValueError):
        return []


def validate_target_url(
    url: str,
    *,
    blocked_hosts: Iterable[str] = (),
    allow_private: bool = True,
    resolver: Resolver = system_resolver,
) -> None:
    """Raise UnsafeTargetError if `url` must not be monitored."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeTargetError("Only http and https URLs can be monitored")
    if parts.username or parts.password:
        raise UnsafeTargetError("URLs with embedded credentials are not allowed")

    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeTargetError("URL has no host")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeTargetError("URL has an invalid port") from exc

    blocked = ALWAYS_BLOCKED_HOSTS | {h.strip().rstrip(".").lower() for h in blocked_hosts if h.strip()}
    if host in blocked or host.endswith(".localhost"):
        raise UnsafeTargetError(f"Host '{host}' is internal and cannot be monitored")

    try:
        addresses = [_parse_ip(host)]
    except ValueError:
        addresses = _resolve(host, port, resolver)
        if not addresses:
            raise UnsafeTargetError(f"Host '{host}' could not be resolved") from None

    for ip in addresses:
        problem = _address_problem(ip, allow_private)
        if problem:
            raise UnsafeTargetError(f"Host '{host}' resolves to a {problem} address, which is not allowed")

    internal_ips = {ip for name in blocked for ip in _resolve(name, port, resolver)}
    if internal_ips.intersection(addresses):
        raise UnsafeTargetError(f"Host '{host}' points at an internal MiniOps service")
