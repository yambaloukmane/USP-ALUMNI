"""Connexion, inscription avec code e-mail, mot de passe oublié."""
import logging
import random
import re
import time

from django.conf import settings
from django.contrib import messages as flash
from django.contrib.auth.hashers import make_password
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .. import data_service as ds
from .. import emails, ratelimit
from ..profile_form import PASSWORD_MIN_LENGTH, choice_context, form_values, parse_profile
from ._common import code_digest, login_member, safe_next, valid_email

log = logging.getLogger(__name__)


# ------------------------------------------------------------------- Connexion
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "GET" and request.session.get("member"):
        return redirect(safe_next(request, reverse("profile")))

    error, email = "", ""
    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        remember = request.POST.get("remember") == "on"

        if not (ratelimit.hit("login-ip", ratelimit.client_ip(request), 20, 600)
                and ratelimit.hit("login-email", email.lower(), 6, 600)):
            error = ratelimit.TOO_MANY
        else:
            status = ds.check_connection()
            if status != "OK":
                error = status
            else:
                member = ds.authenticate(email, password)
                if not member:
                    error = "Email ou mot de passe incorrect."
                elif member.get("status") == "pending":
                    error = "Votre inscription est en attente de validation par un responsable."
                elif member.get("status") == "suspended":
                    error = "Ce compte est suspendu. Contactez un responsable."
                else:
                    login_member(request, member, remember)
                    return redirect(safe_next(request, reverse("profile")))

    return render(request, "alumni/login.html", {
        "error": error, "email": email, "next": request.GET.get("next", ""),
    })


@require_POST
def logout_view(request):
    request.session.flush()
    return redirect("home")


# ------------------------------------------------------------------ Codes e-mail
def _new_code_state(email: str, purpose: str) -> tuple[str, dict]:
    code = f"{random.SystemRandom().randint(0, 999999):06d}"
    return code, {
        "digest": code_digest(email, code, purpose),
        "expires": time.time() + settings.REGISTRATION_CODE_TTL_SECONDS,
        "sent": time.time(),
        "attempts": 0,
    }


def _check_code(state: dict, email: str, raw_code: str, purpose: str) -> tuple[bool, str]:
    """Vérifie un code saisi. Retourne (ok, message d'erreur)."""
    import hmac

    code = re.sub(r"\D", "", raw_code or "")
    if time.time() > state.get("expires", 0):
        return False, "Ce code a expiré. Demandez un nouveau code."
    if state.get("attempts", 0) >= settings.REGISTRATION_CODE_MAX_ATTEMPTS:
        return False, "Trop de tentatives. Demandez un nouveau code."
    if not hmac.compare_digest(code_digest(email, code, purpose), state.get("digest", "")):
        state["attempts"] = state.get("attempts", 0) + 1
        return False, "Code de vérification incorrect. Veuillez réessayer."
    return True, ""


def _dev_hint(request, code: str) -> None:
    if settings.DEBUG and settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
        flash.info(request, f"Mode développement : le code est {code} (aussi affiché dans le terminal).")


# ------------------------------------------------------------------ Inscription
def _send_registration_code(request, pending: dict) -> bool:
    code, state = _new_code_state(pending["data"]["email"], "register")
    pending.update(state)
    try:
        emails.send_code_email(pending["data"]["email"], pending["data"]["first_name"], code, "register")
    except Exception as exc:  # noqa: BLE001
        log.error("Registration mail failed: %s", exc)
        return False
    _dev_hint(request, code)
    return True


@require_http_methods(["GET", "POST"])
def register(request):
    form = form_values((request.session.get("pending_registration") or {}).get("data", {}))
    error, step = "", 1

    if request.method == "POST":
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        data, error, step = parse_profile(request.POST, registration=True)
        form = form_values({**data, "email": email, "school_other": request.POST.get("school_other", "")})

        if not ratelimit.hit("register", ratelimit.client_ip(request), 10, 3600):
            error, step = ratelimit.TOO_MANY, 1
        elif not valid_email(email):
            error, step = "Veuillez entrer une adresse email valide.", 1
        elif len(password) < PASSWORD_MIN_LENGTH:
            error, step = f"Le mot de passe doit contenir au moins {PASSWORD_MIN_LENGTH} caractères.", 1
        elif not error:
            status = ds.check_connection()
            if status != "OK":
                error, step = status, 1
            elif ds.get_member_by_email(email):
                error, step = "Un compte existe déjà avec cet email.", 1
            else:
                data.update({"email": email.lower(), "terms_accepted_at": timezone.now().isoformat()})
                pending = {"data": data, "password_hash": make_password(password)}
                if _send_registration_code(request, pending):
                    request.session["pending_registration"] = pending
                    return redirect("register_verify")
                error, step = "Impossible d'envoyer le code de vérification. Vérifiez l'adresse email.", 1

    return render(request, "alumni/register.html", {
        "error": error, "error_step": step if error else 0, "f": form, **choice_context(form),
        "steps": [(1, "Compte"), (2, "Prépa"), (3, "Situation"), (4, "Réseau")],
    })


@require_http_methods(["GET", "POST"])
def register_verify(request):
    pending = request.session.get("pending_registration")
    if not pending:
        return redirect("register")

    error = ""
    if request.method == "POST":
        email = pending["data"]["email"]
        if not ratelimit.hit("register-verify", ratelimit.client_ip(request), 30, 3600):
            error = ratelimit.TOO_MANY
        else:
            ok, error = _check_code(pending, email, request.POST.get("code", ""), "register")
            request.session["pending_registration"] = pending
            if ok:
                status = ds.check_connection()
                if status != "OK":
                    error = status
                else:
                    needs_approval = settings.REQUIRE_APPROVAL
                    try:
                        member = ds.create_member(
                            pending["data"], pending["password_hash"],
                            status="pending" if needs_approval else "active")
                    except ds.DataError as exc:
                        error = str(exc)
                    else:
                        del request.session["pending_registration"]
                        if needs_approval:
                            return render(request, "alumni/register_done.html", {"pending": True})
                        login_member(request, member)
                        return render(request, "alumni/register_done.html", {"pending": False})

    return render(request, "alumni/register_verify.html", {"error": error, "email": pending["data"]["email"]})


@require_POST
def register_resend(request):
    pending = request.session.get("pending_registration")
    if not pending:
        return redirect("register")
    wait = settings.REGISTRATION_RESEND_DELAY_SECONDS - (time.time() - pending.get("sent", 0))
    if wait > 0:
        flash.error(request, f"Patientez encore {int(wait) + 1} secondes avant de redemander un code.")
    elif not ratelimit.hit("register-resend", ratelimit.client_ip(request), 10, 3600):
        flash.error(request, ratelimit.TOO_MANY)
    elif _send_registration_code(request, pending):
        request.session["pending_registration"] = pending
        flash.success(request, "Un nouveau code vient d'être envoyé.")
    else:
        flash.error(request, "Impossible d'envoyer le code. Réessayez plus tard.")
    return redirect("register_verify")


# ------------------------------------------------------------- Mot de passe oublié
@require_http_methods(["GET", "POST"])
def forgot(request):
    error = ""
    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        if not ratelimit.hit("forgot-ip", ratelimit.client_ip(request), 8, 3600) \
                or not ratelimit.hit("forgot-email", email or "-", 3, 3600):
            error = ratelimit.TOO_MANY
        elif not valid_email(email):
            error = "Veuillez entrer une adresse email valide."
        else:
            member = ds.get_member_by_email(email)
            code, state = _new_code_state(email, "reset")
            state["email"] = email
            state["member_id"] = ""
            if member and member.get("status") != "suspended":
                try:
                    emails.send_code_email(email, member.get("first_name") or "", code, "reset")
                    state["member_id"] = str(member["id"])
                    _dev_hint(request, code)
                except Exception as exc:  # noqa: BLE001
                    log.error("Reset mail failed: %s", exc)
            # Même réponse que l'adresse existe ou non : on ne révèle pas qui a un compte.
            request.session["pending_reset"] = state
            return redirect("forgot_verify")
    return render(request, "alumni/forgot.html", {"error": error})


@require_http_methods(["GET", "POST"])
def forgot_verify(request):
    state = request.session.get("pending_reset")
    if not state:
        return redirect("forgot")

    error = ""
    if request.method == "POST":
        password = request.POST.get("password", "")
        confirm = request.POST.get("confirm", "")
        if not ratelimit.hit("forgot-verify", ratelimit.client_ip(request), 30, 3600):
            error = ratelimit.TOO_MANY
        elif len(password) < PASSWORD_MIN_LENGTH:
            error = f"Le mot de passe doit contenir au moins {PASSWORD_MIN_LENGTH} caractères."
        elif password != confirm:
            error = "Les deux mots de passe ne sont pas identiques."
        else:
            ok, error = _check_code(state, state["email"], request.POST.get("code", ""), "reset")
            request.session["pending_reset"] = state
            if ok and state.get("member_id"):
                try:
                    ds.set_password(state["member_id"], make_password(password))
                except ds.DataError as exc:
                    error = str(exc)
                else:
                    del request.session["pending_reset"]
                    flash.success(request, "Mot de passe modifié. Vous pouvez vous connecter.")
                    return redirect("login")
            elif ok:
                error = "Code de vérification incorrect. Veuillez réessayer."
    return render(request, "alumni/forgot_verify.html", {"error": error, "email": state["email"]})
