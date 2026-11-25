"""Réseau : actualités, emplois, annuaire, événements, galerie."""
import json
import logging
import uuid
from datetime import datetime
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages as flash
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .. import data_service as ds
from .. import ratelimit, storage
from ..decorators import api_member_required, member_required
from ..images import compress_jpeg
from ..profile_form import OFFER_LABELS, SEEK_LABELS, SITUATIONS
from ._common import DEFAULT_NEWS_IMAGE, JOB_TYPES, MAX_TEXT_LENGTH, MAX_UPLOAD_BYTES, session_member

log = logging.getLogger(__name__)

MEMBERS_PER_PAGE = 24
PHOTOS_PER_PAGE = 36
POST_TYPES = {"news", "job"}
MAX_COMMENT_LENGTH = 2000


def is_admin(request) -> bool:
    from .admin_area import is_admin as check

    return check(request)


# ---------------------------------------------------------------- Actualités & emplois
def _apply_link(job: dict) -> tuple[str, bool]:
    """(adresse, ouvre un autre site ?) pour le bouton « Postuler »."""
    contact = (job.get("apply_contact") or "").strip()
    if contact.startswith("https://") or contact.startswith("http://"):
        return contact, True
    if "@" in contact and " " not in contact:
        return f"mailto:{contact}", False
    return reverse("contact"), False


def _post_key(post_type: str, post_id) -> str:
    return f"{post_type}:{post_id}"


def _display_name(member: dict) -> str:
    return f"{member.get('first_name') or ''} {member.get('last_name') or ''}".strip() or "Membre"


@member_required
@ensure_csrf_cookie
def feed(request):
    me = session_member(request)["id"]

    likes = ds.get_likes()
    like_counts: dict[str, int] = {}
    liked_by_me: set[str] = set()
    for like in likes:
        key = _post_key(like["post_type"], like["post_id"])
        like_counts[key] = like_counts.get(key, 0) + 1
        if str(like["member_id"]) == me:
            liked_by_me.add(key)
    comment_counts = ds.get_comment_counts()
    members_by_email = {m["email"]: m for m in ds.get_members() if m.get("email")}

    posts = []
    for item in ds.get_news():
        key = _post_key("news", item["id"])
        posts.append({
            "post_type": "news", "id": item["id"], "title": item["title"], "body": item.get("desc") or "",
            "img": item.get("img") or DEFAULT_NEWS_IMAGE, "date_label": item.get("date") or "",
            "created_at": item.get("created_at") or "", "author": "AEPS-ALUMNI", "author_id": "",
            "initials": "AE", "like_count": like_counts.get(key, 0), "liked": key in liked_by_me,
            "comment_count": comment_counts.get(key, 0),
        })
    for job in ds.get_public_jobs():
        href, external = _apply_link(job)
        key = _post_key("job", job["id"])
        poster = members_by_email.get(job.get("posted_by") or "")
        author = _display_name(poster) if poster else "Un membre du réseau"
        posts.append({
            "post_type": "job", "id": job["id"], "title": job["title"], "body": "",
            "company": job.get("company") or "", "location": job.get("location") or "",
            "salary": job.get("salary") or "", "job_type": job.get("type") or "CDI",
            "expires_at": job.get("expires_at") or "", "apply_href": href, "apply_external": external,
            "created_at": job.get("created_at") or "", "author": author,
            "author_id": str(poster["id"]) if poster else "",
            "initials": "".join(p[:1] for p in author.split()[:2]).upper() or "AL",
            "like_count": like_counts.get(key, 0), "liked": key in liked_by_me,
            "comment_count": comment_counts.get(key, 0),
        })
    posts.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    return render(request, "alumni/feed.html", {"posts": posts, "default_news_image": DEFAULT_NEWS_IMAGE})


def _post_exists(post_type: str, post_id: str) -> bool:
    if post_type == "news":
        return any(str(n["id"]) == str(post_id) for n in ds.get_news())
    if post_type == "job":
        return any(str(j["id"]) == str(post_id) for j in ds.get_jobs())
    return False


@api_member_required
@require_POST
def api_feed_like(request, post_type, post_id):
    if post_type not in POST_TYPES or not _post_exists(post_type, post_id):
        return JsonResponse({"error": "Publication introuvable."}, status=404)
    me = session_member(request)["id"]
    if not ratelimit.hit("feed-like", me, 60, 300):
        return JsonResponse({"error": ratelimit.TOO_MANY}, status=429)
    liked = ds.toggle_like(post_type, post_id, me)
    count = sum(1 for like in ds.get_likes() if like["post_type"] == post_type and str(like["post_id"]) == str(post_id))
    return JsonResponse({"liked": liked, "count": count})


@api_member_required
@require_GET
def api_feed_comments(request, post_type, post_id):
    if post_type not in POST_TYPES:
        return JsonResponse({"error": "Type invalide."}, status=400)
    me = session_member(request)["id"]
    names = {str(m["id"]): _display_name(m) for m in ds.get_members()}
    comments = ds.get_comments(post_type, post_id)
    return JsonResponse({"comments": [{
        "id": c["id"], "body": c["body"], "author": names.get(str(c["member_id"]), "Membre"),
        "mine": str(c["member_id"]) == me, "created_at": c.get("created_at") or "",
    } for c in comments]})


@api_member_required
@require_POST
def api_feed_comment(request, post_type, post_id):
    if post_type not in POST_TYPES or not _post_exists(post_type, post_id):
        return JsonResponse({"error": "Publication introuvable."}, status=404)
    member = session_member(request)
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Requête invalide."}, status=400)
    body = str(payload.get("body", "")).strip()
    if not body or len(body) > min(MAX_COMMENT_LENGTH, MAX_TEXT_LENGTH):
        return JsonResponse({"error": "Commentaire invalide."}, status=400)
    if not ratelimit.hit("feed-comment", member["id"], 20, 600):
        return JsonResponse({"error": ratelimit.TOO_MANY}, status=429)
    try:
        comment = ds.add_comment(post_type, post_id, member["id"], body)
    except ds.DataError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    return JsonResponse({"comment": {
        "id": comment["id"], "body": comment["body"], "author": _display_name(member),
        "mine": True, "created_at": comment.get("created_at") or "",
    }})


@api_member_required
@require_POST
def api_feed_comment_delete(request, comment_id):
    comment = ds.get_comment(comment_id)
    if not comment:
        return JsonResponse({"error": "Commentaire introuvable."}, status=404)
    me = session_member(request)["id"]
    if str(comment["member_id"]) != me and not is_admin(request):
        return JsonResponse({"error": "Action non autorisée."}, status=403)
    ds.delete_comment(comment_id)
    return JsonResponse({"ok": True})


@member_required
@require_http_methods(["GET", "POST"])
def job_propose(request):
    member = session_member(request)
    form = {k: "" for k in ("title", "company", "location", "salary", "apply_contact", "expires_at")}
    form["type"] = "CDI"
    if request.method == "POST":
        form = {k: request.POST.get(k, "").strip()[:200] for k in form}
        if form["type"] not in JOB_TYPES:
            form["type"] = "CDI"
        if not ratelimit.hit("job-propose", member["id"], 5, 3600):
            flash.error(request, ratelimit.TOO_MANY)
        elif not (form["title"] and form["company"] and form["location"] and form["apply_contact"]):
            flash.error(request, "Poste, entreprise, lieu et moyen de postuler sont obligatoires.")
        else:
            expires = form["expires_at"] or None
            try:
                if expires:
                    datetime.strptime(expires, "%Y-%m-%d")
                ds.add_job(form["title"], form["company"], form["location"], form["salary"], form["type"],
                           apply_contact=form["apply_contact"], expires_at=expires,
                           status="pending", posted_by=member["email"])
            except ValueError:
                flash.error(request, "Date d'expiration invalide.")
            except ds.DataError as exc:
                flash.error(request, str(exc))
            else:
                flash.success(request, "Merci ! Votre offre sera visible après validation par un responsable.")
                return redirect("feed")
    return render(request, "alumni/job_propose.html", {"form": form, "job_types": JOB_TYPES})


# ------------------------------------------------------------------------ Annuaire
def _matches(member: dict, filters: dict) -> bool:
    def low(key):
        return str(member.get(key) or "").lower()

    q = filters["q"].lower()
    haystack = " ".join(low(k) for k in ("first_name", "last_name", "job", "sector", "city", "country", "promo",
                                         "company", "school", "track"))
    return (
        (not q or q in haystack)
        and (not filters["promo"] or str(member.get("promo") or "") == filters["promo"])
        and (not filters["sector"] or filters["sector"].lower() in low("sector"))
        and (not filters["country"] or filters["country"].lower() in low("country"))
        and (not filters["mentor"] or bool(member.get("is_mentor")))
        and (not filters["school"] or str(member.get("school") or "") == filters["school"])
        and (not filters["situation"] or str(member.get("situation") or "") == filters["situation"])
    )


def _card(member: dict) -> dict:
    """Données affichées dans l'annuaire : e-mail et téléphone seulement si la personne l'a autorisé."""
    card = {k: v for k, v in member.items() if k not in ("email", "phone", "referent")}
    card["contact_email"] = member.get("email") or "" if member.get("show_email") else ""
    card["contact_phone"] = member.get("phone") or "" if member.get("show_phone") else ""
    card["whatsapp"] = bool(member.get("phone_whatsapp")) and bool(card["contact_phone"])
    card["offers_text"] = ", ".join(OFFER_LABELS[k] for k in member.get("offers") or [] if k in OFFER_LABELS)
    card["seeks_text"] = ", ".join(SEEK_LABELS[k] for k in member.get("seeks") or [] if k in SEEK_LABELS)
    return card


@member_required
def members(request):
    everyone = ds.get_active_members()
    filters = {
        "q": request.GET.get("q", "").strip()[:100],
        "promo": request.GET.get("promo", "").strip()[:10],
        "sector": request.GET.get("sector", "").strip()[:100],
        "country": request.GET.get("country", "").strip()[:100],
        "mentor": request.GET.get("mentor") == "1",
        "school": request.GET.get("school", "").strip()[:100],
        "situation": request.GET.get("situation", "").strip()[:40],
    }
    found = [m for m in everyone if _matches(m, filters)]
    page = Paginator(found, MEMBERS_PER_PAGE).get_page(request.GET.get("page"))
    page.object_list = [_card(m) for m in page.object_list]
    query = urlencode({k: ("1" if v is True else v) for k, v in filters.items() if v})
    return render(request, "alumni/members.html", {
        "page": page,
        "total": len(found),
        "total_all": len(everyone),
        "promos": sorted({m.get("promo") for m in everyone if m.get("promo")}, reverse=True),
        "schools": sorted({m.get("school") for m in everyone if m.get("school")}),
        "situations": SITUATIONS,
        "filters": filters,
        "filters_active": any(filters.values()),
        "query": query,
    })


# -------------------------------------------------------------------- Événements
def _parse_dt(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


@member_required
def events_page(request):
    me = session_member(request)["id"]
    rsvps = ds.get_rsvps()
    counts: dict[str, int] = {}
    mine: set[str] = set()
    for row in rsvps:
        counts[str(row["event_id"])] = counts.get(str(row["event_id"]), 0) + 1
        if str(row["member_id"]) == me:
            mine.add(str(row["event_id"]))

    now = timezone.now()
    upcoming, past = [], []
    for event in ds.get_events():
        starts = _parse_dt(event["starts_at"])
        item = {**event, "starts": starts, "going": str(event["id"]) in mine, "count": counts.get(str(event["id"]), 0)}
        (upcoming if starts and starts >= now else past).append(item)
    past.reverse()
    return render(request, "alumni/events.html", {"upcoming": upcoming, "past": past[:10]})


@member_required
@require_POST
def event_rsvp(request, event_id):
    me = session_member(request)["id"]
    if not any(str(e["id"]) == str(event_id) for e in ds.get_events()):
        flash.error(request, "Événement introuvable.")
        return redirect("events")
    going = any(str(r["event_id"]) == str(event_id) and str(r["member_id"]) == me for r in ds.get_rsvps())
    try:
        ds.set_rsvp(event_id, me, not going)
    except ds.DataError as exc:
        flash.error(request, str(exc))
    else:
        flash.success(request, "Participation annulée." if going else "Participation enregistrée !")
    return redirect("events")


# ----------------------------------------------------------------------- Galerie
@member_required
def gallery_page(request):
    me = session_member(request)["id"]
    admin = is_admin(request)
    photos = ds.get_photos()
    albums = sorted({p.get("album") or "Général" for p in photos})
    album = request.GET.get("album", "")
    if album:
        photos = [p for p in photos if (p.get("album") or "Général") == album]
    page = Paginator(photos, PHOTOS_PER_PAGE).get_page(request.GET.get("page"))
    for photo in page.object_list:
        photo["can_delete"] = admin or str(photo.get("uploaded_by")) == me
    return render(request, "alumni/gallery.html", {
        "page": page, "albums": albums, "album": album, "query": urlencode({"album": album}) if album else "",
    })


@member_required
@require_POST
def gallery_upload(request):
    me = session_member(request)["id"]
    files = request.FILES.getlist("photos")[:10]
    album = (request.POST.get("album", "").strip() or "Général")[:60]
    title = request.POST.get("title", "").strip()[:120]
    if not files:
        flash.error(request, "Aucune photo sélectionnée.")
    elif not ratelimit.hit("gallery", me, 10, 600):
        flash.error(request, ratelimit.TOO_MANY)
    else:
        done = 0
        for uploaded in files:
            if uploaded.size > MAX_UPLOAD_BYTES:
                continue
            try:
                jpeg = compress_jpeg(uploaded, 1600, 80)
                path = f"{me}/{uuid.uuid4().hex}.jpg"
                url = storage.upload(settings.BUCKET_GALLERY, path, jpeg, "image/jpeg")
                ds.add_photo(album, title, url, path, me)
                done += 1
            except Exception as exc:  # noqa: BLE001
                log.info("Gallery upload rejected: %s", exc)
        if done:
            flash.success(request, f"{done} photo(s) ajoutée(s).")
        else:
            flash.error(request, "Aucune photo n'a pu être ajoutée (format ou taille invalide).")
    return redirect("gallery")


@member_required
@require_POST
def gallery_delete(request, photo_id):
    photo = ds.get_photo(photo_id)
    if not photo:
        flash.error(request, "Photo introuvable.")
    elif not (is_admin(request) or str(photo.get("uploaded_by")) == session_member(request)["id"]):
        flash.error(request, "Vous ne pouvez supprimer que vos propres photos.")
    else:
        try:
            ds.delete_photo(photo_id)
            storage.remove(settings.BUCKET_GALLERY, photo.get("path", ""))
            flash.success(request, "Photo supprimée.")
        except ds.DataError as exc:
            flash.error(request, str(exc))
    return redirect("gallery")
