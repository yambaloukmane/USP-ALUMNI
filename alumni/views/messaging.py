"""Messagerie privée, discussion de groupe par promotion, messages vocaux."""
import json
import logging
import re
import uuid

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .. import data_service as ds
from .. import ratelimit, storage
from ..decorators import api_member_required, member_required
from ._common import MAX_TEXT_LENGTH, session_member, valid_email

log = logging.getLogger(__name__)

CALL_RE = re.compile(r"^\[CALL\](audio|video):[A-Za-z0-9-]{8,64}$")
MAX_VOICE_BYTES = 5 * 1024 * 1024
VOICE_EXTENSIONS = {"audio/webm": "webm", "video/webm": "webm", "audio/ogg": "ogg", "audio/mp4": "m4a",
                    "audio/mpeg": "mp3", "audio/wav": "wav"}


def _room_of(member_id: str) -> str:
    """Salle de discussion de la promotion du membre ('' s'il n'a pas de promotion)."""
    member = ds.get_member_cached(member_id) or {}
    promo = (member.get("promo") or "").strip()
    return f"{ds.GROUP_PREFIX}{promo}" if promo else ""


def _preview(text: str) -> str:
    if text.startswith("[AUDIO]"):
        return "🎤 Message vocal"
    if text.startswith("[CALL]"):
        return "📞 Appel"
    return text[:120]


def _names() -> dict[str, str]:
    return {m["email"]: f"{m.get('first_name') or ''} {m.get('last_name') or ''}".strip() or m["email"]
            for m in ds.get_members() if m.get("email")}


def _public_message(msg: dict, me: str, names: dict[str, str] | None = None) -> dict:
    out = {"id": msg["id"], "mine": msg["sender_id"] == me, "text": msg["text"],
           "time": msg["time"], "created_at": msg["created_at"]}
    if names is not None:
        out["sender"] = names.get(msg["sender_id"], "Membre")
    return out


@member_required
@ensure_csrf_cookie
def messages_page(request):
    member = session_member(request)
    config = {
        "me": {"email": member["email"], "first_name": member["first_name"], "last_name": member["last_name"]},
        "urls": {
            "contacts": reverse("api_contacts"), "conversation": reverse("api_conversation"),
            "send": reverse("api_send"), "unread": reverse("api_unread"), "voice": reverse("api_voice"),
        },
    }
    return render(request, "alumni/messages.html", {"chat_config": config})


@api_member_required
@require_GET
def api_contacts(request):
    me = session_member(request)
    summaries = ds.get_contact_summaries(me["email"])

    contacts = []
    for m in ds.get_active_members():
        if not m.get("email") or m["email"] == me["email"]:
            continue
        s = summaries.get(m["email"])
        contacts.append({
            "id": m["email"], "member_id": m.get("id"),
            "first_name": m.get("first_name") or "Inconnu", "last_name": m.get("last_name") or "",
            "promo": m.get("promo") or "N/A", "job": m.get("job") or "Membre",
            "lastMessage": _preview(s["last_text"]) if s else "Démarrer une discussion...",
            "lastTime": s["last_time"] if s else "", "lastAt": str(s["last_at"]) if s else "",
            "unread": int(s["unread"]) if s else 0,
        })
    contacts.sort(key=lambda c: c["lastAt"], reverse=True)

    room = _room_of(me["id"])
    if room:
        last = ds.get_group_last(room)
        names = _names()
        preview = "Discussion de la promotion"
        if last:
            who = "Moi" if last["sender_id"] == me["email"] else names.get(last["sender_id"], "Membre").split(" ")[0]
            preview = f"{who} : {_preview(last['text'])}"
        contacts.insert(0, {
            "id": room, "member_id": None, "group": True, "first_name": f"Promo {room[len(ds.GROUP_PREFIX):]}",
            "last_name": "", "promo": room[len(ds.GROUP_PREFIX):], "job": "Discussion de groupe",
            "lastMessage": preview, "lastTime": last["time"] if last else "", "lastAt": "",
            "unread": 0,
        })
    total_unread = sum(c["unread"] for c in contacts)
    return JsonResponse({"contacts": contacts, "total_unread": total_unread})


@api_member_required
@require_GET
def api_conversation(request):
    me = session_member(request)
    other = request.GET.get("with", "").strip()
    after = request.GET.get("after") or None
    try:
        if ds.is_group(other):
            if other != _room_of(me["id"]):
                return JsonResponse({"error": "Accès refusé."}, status=403)
            msgs = ds.get_group_conversation(other, after=after)
            return JsonResponse({"messages": [_public_message(m, me["email"], _names()) for m in msgs]})
        msgs = ds.get_conversation(me["email"], other, after=after)
    except ValueError:
        return JsonResponse({"error": "Contact invalide."}, status=400)

    if any(m["receiver_id"] == me["email"] and not m.get("is_read") for m in msgs):
        ds.mark_as_read(me["email"], other)
    return JsonResponse({"messages": [_public_message(m, me["email"]) for m in msgs]})


def _valid_text(text: str) -> bool:
    if text.startswith("[AUDIO]"):
        url = text[len("[AUDIO]"):]
        return url.startswith("https://") and len(url) <= 600 and " " not in url
    if text.startswith("[CALL]"):
        return bool(CALL_RE.match(text))
    return len(text) <= MAX_TEXT_LENGTH


@api_member_required
@require_POST
def api_send(request):
    me = session_member(request)
    if not ratelimit.hit("send", me["id"], 60, 60):
        return JsonResponse({"error": ratelimit.TOO_MANY}, status=429)
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Requête invalide."}, status=400)

    to = str(payload.get("to", "")).strip()
    text = str(payload.get("text", ""))
    if not to or not text.strip() or to == me["email"]:
        return JsonResponse({"error": "Message ou destinataire invalide."}, status=400)
    if not _valid_text(text):
        return JsonResponse({"error": "Message invalide ou trop long."}, status=400)

    if ds.is_group(to):
        if to != _room_of(me["id"]):
            return JsonResponse({"error": "Accès refusé."}, status=403)
        if text.startswith("[CALL]"):
            return JsonResponse({"error": "Les appels ne sont pas disponibles dans un groupe."}, status=400)
    elif not valid_email(to) or not any(m["email"] == to for m in ds.get_active_members()):
        return JsonResponse({"error": "Destinataire invalide."}, status=400)

    try:
        saved = ds.save_message(me["email"], to, text, timezone.localtime().strftime("%H:%M"))
    except ValueError:
        return JsonResponse({"error": "Destinataire invalide."}, status=400)
    except ds.DataError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    return JsonResponse({"message": _public_message(saved, me["email"], _names() if ds.is_group(to) else None)})


@api_member_required
@require_POST
def api_voice(request):
    """Reçoit un message vocal, le range dans Supabase Storage et renvoie son adresse."""
    me = session_member(request)
    audio = request.FILES.get("audio")
    if not audio:
        return JsonResponse({"error": "Aucun enregistrement."}, status=400)
    content_type = (audio.content_type or "").split(";")[0].lower()
    if content_type not in VOICE_EXTENSIONS:
        return JsonResponse({"error": "Format audio non pris en charge."}, status=400)
    if audio.size > MAX_VOICE_BYTES:
        return JsonResponse({"error": "Enregistrement trop long."}, status=413)
    if not ratelimit.hit("voice", me["id"], 20, 600):
        return JsonResponse({"error": ratelimit.TOO_MANY}, status=429)
    try:
        url = storage.upload(settings.BUCKET_VOICE, f"{me['id']}/{uuid.uuid4().hex}.{VOICE_EXTENSIONS[content_type]}",
                             audio.read(), content_type)
    except storage.StorageError as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    return JsonResponse({"url": url})


@api_member_required
@require_GET
def api_unread(request):
    return JsonResponse({"unread": ds.get_unread_count(session_member(request)["email"])})

