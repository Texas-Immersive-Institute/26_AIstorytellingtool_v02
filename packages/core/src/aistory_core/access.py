"""Who is calling: the host computer itself, a LAN device, or neither."""

from __future__ import annotations

import ipaddress


def is_loopback(peer: str | None) -> bool:
    if not peer:
        return False
    if peer == "localhost":
        return True
    try:
        return ipaddress.ip_address(peer).is_loopback
    except ValueError:
        return False


def is_lan(peer: str | None) -> bool:
    """A private (LAN) address that is not the host itself."""
    if not peer or is_loopback(peer):
        return False
    try:
        ip = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return ip.is_private and not ip.is_link_local
