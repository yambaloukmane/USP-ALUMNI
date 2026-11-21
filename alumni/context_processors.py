from pathlib import Path

from django.conf import settings
from django.urls import reverse


def _asset_version() -> int:
    """Date de modification du CSS/JS : change à chaque mise à jour, ce qui force les navigateurs à recharger."""
    static = Path(__file__).resolve().parent / "static" / "alumni"
    try:
        return int(max(p.stat().st_mtime for p in [*(static / "css").glob("*.css"), *(static / "js").glob("*.js")]) // 1)
    except (OSError, ValueError):
        return 0


ASSET_VERSION = _asset_version()


def site(request):
    """Variables disponibles dans tous les templates (navbar, footer...)."""
    member = request.session.get("member") if hasattr(request, "session") else None
    return {
        "current_member": member,
        "avatar_version": request.session.get("avatar_v", 0) if member else 0,
        "is_admin": bool(request.session.get("is_admin")) if hasattr(request, "session") else False,
        "nav_links": [(reverse("feed"), "Actualités et emplois"), (reverse("members"), "Annuaire"),
                      (reverse("events"), "Événements"), (reverse("gallery"), "Galerie"),
                      (reverse("treasury"), "Cotisations")] if member else [],
        "asset_v": ASSET_VERSION,
        "contact_email": settings.CONTACT_EMAIL,
        "contact_phone": settings.CONTACT_PHONE,
    }
