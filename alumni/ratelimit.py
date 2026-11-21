"""Limitation du nombre de tentatives (connexion, codes, envois...).

Les compteurs vivent dans le cache Django : en mémoire locale par défaut, partagés
entre processus si REDIS_URL est défini.
"""
from django.conf import settings
from django.core.cache import cache

TOO_MANY = "Trop de tentatives. Réessayez dans quelques minutes."


def client_ip(request) -> str:
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def hit(scope: str, ident: str, limit: int, window: int) -> bool:
    """Compte une tentative. Retourne True si elle est autorisée, False si la limite est dépassée."""
    key = f"rl:{scope}:{ident}"
    if cache.add(key, 1, window):
        return True
    try:
        return cache.incr(key) <= limit
    except ValueError:  # la clé a expiré entre-temps
        cache.set(key, 1, window)
        return True
