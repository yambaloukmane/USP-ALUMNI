"""Espace Responsable : tableau de bord, membres, actualités, emplois, événements, cotisations, exports."""
import csv
import hmac
import logging
from collections import Counter
from datetime import datetime
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages as flash
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .. import data_service as ds
from .. import emails, ratelimit
from ..decorators import admin_required
from ._common import DEFAULT_NEWS_IMAGE, JOB_TYPES, external_url
from .network import _parse_dt

log = logging.getLogger(__name__)

ADMIN_TABS = ("dashboard", "members", "news", "jobs", "events", "dues")
TAB_LABELS = [("dashboard", "Tableau de bord"), ("members", "Membres"), ("news", "Actualités"),
              ("jobs", "Emplois"), ("events", "Événements"), ("dues", "Cotisations")]


def is_admin(request) -> bool:
    """Accès par mot de passe responsable, ou par rôle « admin » (revérifié à chaque requête)."""
    session = request.session
    if not session.get("is_admin"):
        return False
    if session.get("admin_via") == "role":
        member = ds.get_member_cached((session.get("member") or {}).get("id", ""))
        return bool(member and member.get("role") == "admin" and (member.get("status") or "active") == "active")
    return True


def _back_to(tab: str):
    return redirect(f"{reverse('responsable')}?tab={tab}")


def _safe_cell(value):
    """Empêche l'injection de formules quand le CSV est ouvert dans Excel."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _csv(filename: str, header: list[str], rows) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("﻿")  # Excel lit ainsi correctement les accents
    writer = csv.writer(response, delimiter=";")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_safe_cell(v) for v in row])
    return response


# ----------------------------------------------------------------------- Accès
@require_http_methods(["GET", "POST"])
def responsable(request):
    if not is_admin(request):
        error = ""
        if request.method == "POST":
            supplied, expected = request.POST.get("password", ""), settings.ADMIN_PASSWORD
            if not ratelimit.hit("admin-login", ratelimit.client_ip(request), 6, 900):
                error = ratelimit.TOO_MANY
            elif not expected:
                error = "L'accès Responsable n'est pas configuré (ADMIN_PASSWORD manquant)."
            elif hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
                request.session["is_admin"] = True
                request.session["admin_via"] = "password"
                return redirect("responsable")
            else:
                error = "Mot de passe incorrect"
        return render(request, "alumni/responsable_login.html", {"error": error})

    tab = request.GET.get("tab", "dashboard")
    if tab not in ADMIN_TABS:
        tab = "dashboard"
    return render(request, "alumni/responsable.html", _context(request, tab))


@require_POST
def responsable_logout(request):
    request.session.pop("is_admin", None)
    request.session.pop("admin_via", None)
    return redirect("responsable")


# ------------------------------------------------------------------ Contenu des onglets
def _context(request, tab: str) -> dict:
    members = ds.get_members()
    ctx = {"schema_missing": not ds.schema_v3(), "tab": tab, "tabs": ADMIN_TABS, "tab_labels": TAB_LABELS, "job_types": JOB_TYPES, "default_news_image": DEFAULT_NEWS_IMAGE,
           "me_id": (request.session.get("member") or {}).get("id", "")}
    pending = [m for m in members if m.get("status") == "pending"]
    ctx["pending_count"] = len(pending) + sum(1 for j in ds.get_jobs() if j.get("status") == "pending")

    if tab == "dashboard":
        year = timezone.localdate().year
        dues = ds.get_dues(year)
        paid = [d for d in dues if d["status"] == "paid"]
        active = [m for m in members if (m.get("status") or "active") == "active"]
        by_promo = sorted(Counter(m.get("promo") or "—" for m in active).items(), reverse=True)[:12]
        by_country = Counter((m.get("country") or "").strip() for m in active if (m.get("country") or "").strip()
                             and m.get("country") not in ("Non défini",)).most_common(8)
        top = max([n for _, n in by_promo] + [1])
        top_c = max([n for _, n in by_country] + [1])
        ctx["stats"] = {
            "members": len(active), "pending": len(pending), "mentors": sum(1 for m in active if m.get("is_mentor")),
            "jobs": len(ds.get_public_jobs()), "news": len(ds.get_news()),
            "events": sum(1 for e in ds.get_events() if (_parse_dt(e["starts_at"]) or timezone.now()) >= timezone.now()),
            "photos": len(ds.get_photos()), "year": year,
            "dues_total": len(dues), "dues_paid": len(paid),
            "dues_sum": sum(int(d["amount"]) for d in paid),
            "dues_rate": round(100 * len(paid) / len(dues)) if dues else 0,
            "currency": settings.DUES_CURRENCY,
            "by_promo": [(p, n, round(100 * n / top)) for p, n in by_promo],
            "by_country": [(c, n, round(100 * n / top_c)) for c, n in by_country],
        }
        s_ = ctx["stats"]
        ctx["kpis"] = [("Membres actifs", s_["members"]), ("À valider", s_["pending"]), ("Mentors", s_["mentors"]),
                       ("Offres en ligne", s_["jobs"]), ("Actualités", s_["news"]), ("Événements à venir", s_["events"]),
                       ("Photos", s_["photos"]), ("Cotisations payées", f"{s_['dues_rate']} %")]
    elif tab == "members":
        promo = request.GET.get("promo", "").strip()[:10]
        shown = [m for m in members if not promo or str(m.get("promo") or "") == promo]
        ctx["members"] = sorted(shown, key=lambda m: (m.get("status") != "pending", (m.get("last_name") or "").lower()))
        ctx["promo"] = promo
        ctx["promos"] = sorted({str(m["promo"]) for m in members if m.get("promo")}, reverse=True)
    elif tab == "news":
        ctx["news"] = ds.get_news()
    elif tab == "jobs":
        today = datetime.now().date().isoformat()
        jobs = [{**j, "expired": bool(j.get("expires_at")) and str(j["expires_at"]) < today} for j in ds.get_jobs()]
        ctx["jobs"] = sorted(jobs, key=lambda j: j.get("status") != "pending")
    elif tab == "events":
        by_id = {str(m["id"]): m for m in members}
        attendees: dict[str, list[str]] = {}
        for row in ds.get_rsvps():
            m = by_id.get(str(row["member_id"]))
            if m:
                attendees.setdefault(str(row["event_id"]), []).append(f"{m.get('first_name', '')} {m.get('last_name', '')}".strip())
        ctx["events"] = [{**e, "starts": _parse_dt(e["starts_at"]), "attendees": sorted(attendees.get(str(e["id"]), []))}
                         for e in ds.get_events()]
    elif tab == "dues":
        year = int(request.GET.get("year") or timezone.localdate().year)
        by_id = {str(m["id"]): m for m in members}
        rows = []
        for due in ds.get_dues(year):
            m = by_id.get(str(due["member_id"]))
            if m:
                rows.append({**due, "name": f"{m.get('last_name', '')} {m.get('first_name', '')}".strip(), "promo": m.get("promo", "")})
        rows.sort(key=lambda r: (r["status"] == "paid", r["name"].lower()))
        configured_rate = ds.get_due_rate(year)
        ctx.update(year=year, dues=rows, default_amount=configured_rate or settings.DUES_AMOUNT,
                   configured_rate=configured_rate, currency=settings.DUES_CURRENCY,
                   paid_count=sum(1 for r in rows if r["status"] == "paid"),
                   paid_sum=sum(int(r["amount"]) for r in rows if r["status"] == "paid"))
    return ctx


def _run(request, action, success: str, tab: str):
    try:
        action()
        flash.success(request, success)
    except ds.DataError as exc:
        flash.error(request, str(exc))
    return _back_to(tab)


# ----------------------------------------------------------------------- Membres
@admin_required
@require_POST
def member_delete(request, member_id):
    if member_id == request.session.get("member", {}).get("id"):
        flash.error(request, "Vous ne pouvez pas supprimer votre propre compte ici.")
        return _back_to("members")
    return _run(request, lambda: ds.delete_member(member_id), "Membre supprimé.", "members")


@admin_required
@require_POST
def member_role(request, member_id):
    role = request.POST.get("role", "")
    if role not in ("member", "admin"):
        flash.error(request, "Rôle invalide.")
        return _back_to("members")
    if member_id == request.session.get("member", {}).get("id"):
        flash.error(request, "Vous ne pouvez pas modifier votre propre rôle.")
        return _back_to("members")
    return _run(request, lambda: ds.admin_update_member(member_id, {"role": role}),
                "Rôle modifié.", "members")


@admin_required
@require_POST
def member_status(request, member_id):
    status = request.POST.get("status", "")
    if status not in ("active", "suspended"):
        flash.error(request, "Statut invalide.")
        return _back_to("members")
    member = ds.get_member_cached(member_id) or {}
    result = _run(request, lambda: ds.admin_update_member(member_id, {"status": status}),
                  "Inscription validée." if member.get("status") == "pending" else "Statut modifié.", "members")
    if status == "active" and member.get("status") == "pending" and member.get("email"):
        login_url = external_url(f"{reverse('login')}?next={quote(reverse('welcome'))}")
        emails.send_welcome_email(member["email"], member.get("first_name", ""), login_url)
    return result


# ------------------------------------------------------------------- Actualités
@admin_required
@require_POST
def news_add(request):
    title, desc, img = (request.POST.get(k, "").strip() for k in ("title", "desc", "img"))
    if not title or not desc:
        flash.error(request, "Le titre et le contenu sont obligatoires.")
    elif img and not img.startswith(("http://", "https://")):
        flash.error(request, "L'URL de l'image doit commencer par http:// ou https://.")
    else:
        try:
            ds.add_news(title, desc, img or DEFAULT_NEWS_IMAGE, datetime.now().strftime("%d/%m/%Y"))
        except ds.DataError as exc:
            flash.error(request, str(exc))
        else:
            if request.POST.get("notify") == "on":
                emails.notify_members(
                    f"[AEPS-ALUMNI] {title}", f"{title}\n\n{desc}\n\nLire sur le site : {external_url(reverse('feed'))}\n",
                    [m["email"] for m in ds.get_active_members()])
                flash.success(request, "Actualité publiée et envoyée par e-mail aux membres.")
            else:
                flash.success(request, "Actualité publiée.")
    return _back_to("news")


@admin_required
@require_POST
def news_edit(request, news_id):
    title, desc, img = (request.POST.get(k, "").strip() for k in ("title", "desc", "img"))
    if not title or not desc:
        flash.error(request, "Le titre et le contenu sont obligatoires.")
        return _back_to("news")
    if img and not img.startswith(("http://", "https://")):
        flash.error(request, "L'URL de l'image doit commencer par http:// ou https://.")
        return _back_to("news")
    return _run(request, lambda: ds.update_news(news_id, title, desc, img or DEFAULT_NEWS_IMAGE),
                "Actualité modifiée.", "news")


@admin_required
@require_POST
def news_delete(request, news_id):
    return _run(request, lambda: ds.delete_news(news_id), "Actualité supprimée.", "news")


# ----------------------------------------------------------------------- Emplois
def _job_fields(request) -> dict | None:
    fields = {k: request.POST.get(k, "").strip()[:200] for k in
              ("title", "company", "location", "salary", "apply_contact", "expires_at")}
    fields["type"] = request.POST.get("type", "CDI") if request.POST.get("type") in JOB_TYPES else "CDI"
    if not (fields["title"] and fields["company"] and fields["location"]):
        flash.error(request, "Poste, entreprise et localisation sont obligatoires.")
        return None
    if fields["expires_at"]:
        try:
            datetime.strptime(fields["expires_at"], "%Y-%m-%d")
        except ValueError:
            flash.error(request, "Date d'expiration invalide.")
            return None
    return fields


@admin_required
@require_POST
def job_add(request):
    f = _job_fields(request)
    if not f:
        return _back_to("jobs")
    return _run(request, lambda: ds.add_job(
        f["title"], f["company"], f["location"], f["salary"], f["type"],
        apply_contact=f["apply_contact"], expires_at=f["expires_at"] or None, status="approved"),
        "Offre ajoutée.", "jobs")


@admin_required
@require_POST
def job_edit(request, job_id):
    f = _job_fields(request)
    if not f:
        return _back_to("jobs")
    return _run(request, lambda: ds.update_job(job_id, f), "Offre modifiée.", "jobs")


@admin_required
@require_POST
def job_approve(request, job_id):
    return _run(request, lambda: ds.update_job(job_id, {"status": "approved"}), "Offre validée.", "jobs")


@admin_required
@require_POST
def job_delete(request, job_id):
    return _run(request, lambda: ds.delete_job(job_id), "Offre supprimée.", "jobs")


# ------------------------------------------------------------------- Événements
@admin_required
@require_POST
def event_add(request):
    title, description, location, when = (request.POST.get(k, "").strip() for k in ("title", "description", "location", "starts_at"))
    try:
        starts = timezone.make_aware(datetime.strptime(when, "%Y-%m-%dT%H:%M"))
    except ValueError:
        flash.error(request, "Date et heure invalides.")
        return _back_to("events")
    if not title:
        flash.error(request, "Le titre est obligatoire.")
        return _back_to("events")
    result = _run(request, lambda: ds.add_event(title, description, location, starts.isoformat()),
                  "Événement créé.", "events")
    if request.POST.get("notify") == "on":
        emails.notify_members(
            f"[AEPS-ALUMNI] Nouvel événement : {title}",
            f"{title}\n{timezone.localtime(starts).strftime('%d/%m/%Y à %H:%M')} — {location}\n\n{description}\n\n"
            f"Répondre sur le site : {external_url(reverse('events'))}\n",
            [m["email"] for m in ds.get_active_members()])
    return result


@admin_required
@require_POST
def event_delete(request, event_id):
    return _run(request, lambda: ds.delete_event(event_id), "Événement supprimé.", "events")


# ------------------------------------------------------------------- Cotisations
def _year_of(request) -> int:
    try:
        return int(request.POST.get("year") or timezone.localdate().year)
    except ValueError:
        return timezone.localdate().year


def _parsed_amount(request) -> int | None:
    try:
        amount = int(request.POST.get("amount") or 0)
    except ValueError:
        amount = 0
    if amount <= 0:
        flash.error(request, "Montant invalide.")
        return None
    return amount


@admin_required
@require_POST
def dues_set_rate(request):
    """Fixe le montant de la cotisation pour l'année et l'applique immédiatement à tous les membres actifs,
    sans exception : crée la cotisation de ceux qui n'en ont pas encore et aligne le montant de celles
    déjà créées mais pas encore payées. Sert aussi de référence pour tout nouveau membre à l'avenir."""
    year = _year_of(request)
    amount = _parsed_amount(request)
    if amount is None:
        return redirect(f"{reverse('responsable')}?tab=dues&year={year}")
    try:
        ds.set_due_rate(year, amount)
        created, updated = ds.apply_due_rate(year, amount, [m["id"] for m in ds.get_active_members()])
        details = ", ".join(p for p in (f"{created} créée(s)" if created else "",
                                         f"{updated} mise(s) à jour" if updated else "") if p)
        suffix = f" ({details})" if details else ""
        flash.success(request, f"Montant {year} fixé à {amount} {settings.DUES_CURRENCY} pour tous les membres actifs{suffix}.")
    except ds.DataError as exc:
        flash.error(request, str(exc))
    return redirect(f"{reverse('responsable')}?tab=dues&year={year}")


@admin_required
@require_POST
def dues_toggle(request, due_id):
    due = ds.get_due(due_id)
    if not due:
        flash.error(request, "Cotisation introuvable.")
        return _back_to("dues")
    try:
        if due["status"] == "paid":
            ds.mark_due_pending(due_id)
            flash.success(request, "Cotisation remise en attente.")
        else:
            ds.mark_due_paid(due_id, "manuel")
            flash.success(request, "Paiement enregistré.")
    except ds.DataError as exc:
        flash.error(request, str(exc))
    return redirect(f"{reverse('responsable')}?tab=dues&year={due['year']}")


# ------------------------------------------------------------------------ Exports
def _members_of(request, active_only: bool = False) -> tuple[list[dict], str]:
    """Membres filtrés par promotion (?promo=2020), triés par nom."""
    promo = request.GET.get("promo", "").strip()[:10]
    found = [m for m in ds.get_members()
             if (not promo or str(m.get("promo") or "") == promo)
             and (not active_only or (m.get("status") or "active") == "active")]
    found.sort(key=lambda m: ((m.get("last_name") or "").lower(), (m.get("first_name") or "").lower()))
    return found, promo


@admin_required
def members_print(request):
    """Liste imprimable (A4) des membres, par promotion ou au complet."""
    found, promo = _members_of(request, active_only=request.GET.get("all") != "1")
    return render(request, "alumni/members_print.html", {
        "members": found, "promo": promo, "total": len(found), "today": timezone.localdate(),
        "with_signature": request.GET.get("signature") == "1",
    })


@admin_required
def export_members(request):
    members, _ = _members_of(request)
    rows = [(m.get("last_name"), m.get("first_name"), m.get("email"), m.get("promo"), m.get("job"),
             m.get("sector"), m.get("city"), m.get("country"), "oui" if m.get("is_mentor") else "non",
             m.get("status"), m.get("role"), m.get("linkedin"),
             m.get("phone"), "oui" if m.get("phone_whatsapp") else "non", m.get("situation"), m.get("company"),
             m.get("school"), m.get("school_track"), m.get("track"), m.get("entry_year"),
             ", ".join(m.get("offers") or []), ", ".join(m.get("seeks") or []), m.get("referent"))
            for m in members]
    return _csv("membres-aeps-alumni.csv",
                ["Nom", "Prénom", "Email", "Promotion", "Statut/Métier", "Secteur", "Ville", "Pays",
                 "Mentor", "Statut du compte", "Rôle", "LinkedIn", "Téléphone", "WhatsApp", "Situation", "Entreprise/école",
                 "École intégrée", "Filière à l'école", "Filière Prépa", "Entrée Prépa", "Propose", "Cherche",
                 "Référent"], rows)


@admin_required
def export_dues(request):
    year = int(request.GET.get("year") or timezone.localdate().year)
    by_id = {str(m["id"]): m for m in ds.get_members()}
    rows = []
    for d in ds.get_dues(year):
        m = by_id.get(str(d["member_id"]), {})
        rows.append((m.get("last_name"), m.get("first_name"), m.get("email"), m.get("promo"), d["year"], d["amount"],
                     "payée" if d["status"] == "paid" else "en attente", d.get("method"), d.get("paid_at")))
    return _csv(f"cotisations-{year}.csv",
                ["Nom", "Prénom", "Email", "Promotion", "Année", "Montant", "Statut", "Moyen", "Payée le"], rows)

