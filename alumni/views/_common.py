"""Fonctions et constantes partagées entre les vues."""
import hashlib
import hmac
import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

DEFAULT_NEWS_IMAGE = (
    "https://images.unsplash.com/photo-1504711434969-e33886168f5c"
    "?q=80&w=600&h=400&auto=format&fit=crop"
)
JOB_TYPES = ["CDI", "CDD", "Stage", "Alternance", "Freelance"]
MAX_TEXT_LENGTH = 10_000
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
from ..profile_form import PASSWORD_MIN_LENGTH  # noqa: E402,F401  (8 caractères minimum)


def session_member(request) -> dict:
    return request.session["member"]


def login_member(request, member: dict, remember: bool = True) -> None:
    request.session["member"] = {
        "id": str(member["id"]),
        "email": member["email"],
        "first_name": member.get("first_name") or "",
        "last_name": member.get("last_name") or "",
    }
    request.session["avatar_v"] = int(time.time())
    if member.get("role") == "admin":
        request.session["is_admin"] = True
        request.session["admin_via"] = "role"
    request.session.set_expiry(settings.SESSION_COOKIE_AGE if remember else 0)


def safe_next(request, fallback: str) -> str:
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


def valid_email(value: str) -> bool:
    try:
        validate_email(value)
        return True
    except ValidationError:
        return False


def code_digest(email: str, code: str, purpose: str) -> str:
    """Empreinte du code (le code lui-même n'est jamais stocké). `purpose` empêche de réutiliser un code d'inscription pour une réinitialisation."""
    key = settings.SECRET_KEY.encode("utf-8")
    return hmac.new(key, f"{purpose}:{email.lower()}:{code}".encode(), hashlib.sha256).hexdigest()


def external_url(path: str) -> str:
    return settings.SITE_URL.rstrip("/") + path


def url_of(name: str, *args) -> str:
    return reverse(name, args=args)
