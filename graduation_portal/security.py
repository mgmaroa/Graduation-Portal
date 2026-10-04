"""Rate limiting and client-IP helpers for the public lookup."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import LookupAttempt


def get_client_ip(request) -> str:
    """
    Real client IP. Behind a reverse proxy (nginx etc.) set TRUST_PROXY_HEADERS=True
    so the address added by YOUR proxy (last X-Forwarded-For entry) is used.
    Never enable it without a proxy, or clients could fake their IP.
    """
    ip = request.META.get("REMOTE_ADDR", "")
    if getattr(settings, "TRUST_PROXY_HEADERS", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            ip = forwarded.split(",")[-1].strip()
    return ip or "0.0.0.0"


def is_rate_limited(ip: str) -> bool:
    """
    Block an IP that makes too many lookups, or too many that find nothing
    (the pattern of someone guessing admission numbers) inside the window.
    Limits are generous on purpose: many students share the campus Wi-Fi IP.
    """
    since = timezone.now() - timedelta(minutes=settings.LOOKUP_WINDOW_MINUTES)
    recent = LookupAttempt.objects.filter(ip_address=ip, created_at__gte=since)
    if recent.count() >= settings.LOOKUP_MAX_TOTAL:
        return True
    return recent.filter(found=False).count() >= settings.LOOKUP_MAX_NOT_FOUND
