from functools import wraps
from urllib.parse import quote

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse


def member_required(view):
    """Page réservée aux membres connectés."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("member"):
            return redirect(f"{reverse('login')}?next={quote(request.get_full_path())}")
        return view(request, *args, **kwargs)

    return wrapper


def api_member_required(view):
    """Point d'accès JSON réservé aux membres connectés."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("member"):
            return JsonResponse({"error": "Connexion requise."}, status=401)
        return view(request, *args, **kwargs)

    return wrapper


def admin_required(view):
    """Page réservée à l'espace Responsable."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        from .views.admin_area import is_admin  # import tardif : évite une dépendance circulaire

        if not is_admin(request):
            return redirect("responsable")
        return view(request, *args, **kwargs)

    return wrapper
