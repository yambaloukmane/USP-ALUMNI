"""Couche d'accès aux données Supabase.

Toutes les lectures/écritures passent par ici ; les vues n'appellent jamais Supabase
directement, ce qui permet de les tester avec un faux client (voir alumni/tests/fakes.py).

- les mots de passe ne sont jamais renvoyés au navigateur et sont hachés ;
- les listes lues souvent (membres, actualités, emplois, événements, photos) sont mises en cache
  quelques secondes et vidées à chaque écriture ;
- la messagerie ne lit que les messages de l'utilisateur connecté.
"""
import hmac
import logging
import re
from datetime import date, datetime, timezone

from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.core.cache import cache

from .supabase_client import get_client

log = logging.getLogger(__name__)

LIST_TTL = 30
AVATAR_TTL = 300
CONN_TTL = 60

LEGACY_COLUMNS = (
    "id,email,first_name,last_name,promo,job,sector,city,country,bio,linkedin,is_mentor,role,status,created_at"
)
V3_FIELDS = (
    "phone_whatsapp", "entry_year", "track", "school", "school_track", "referent", "situation", "company",
    "offers", "seeks", "show_email", "show_phone", "terms_accepted_at",
)
EDITABLE_FIELDS = {
    "first_name", "last_name", "phone", "promo", "job", "sector", "city", "country",
    "bio", "avatar", "linkedin", "is_mentor", *V3_FIELDS,
}
ADMIN_FIELDS = {"role", "status"}
MESSAGE_COLUMNS = "id,sender_id,receiver_id,text,time,is_read,created_at"
GROUP_PREFIX = "promo:"

_UNSAFE_FILTER_VALUE = re.compile(r'[,()"\\\s]')


class DataError(Exception):
    """Erreur lisible côté utilisateur (message en français)."""


# --------------------------------------------------------------------- Outils
def _table(name: str):
    return get_client().table(name)


def _safe(value: str) -> str:
    """Valide une valeur avant de l'insérer dans un filtre PostgREST `or(...)`."""
    value = (value or "").strip()
    if not value or _UNSAFE_FILTER_VALUE.search(value):
        raise ValueError("Valeur de filtre invalide.")
    return value


def _rows(response) -> list[dict]:
    return list(response.data or [])


def _cached_list(key: str, query, ttl: int = LIST_TTL) -> list[dict]:
    """Lit une liste en cache ; en cas d'erreur réseau, renvoie [] SANS mettre l'erreur en cache."""
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        rows = _rows(query())
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch %s failed: %s", key, exc)
        return []
    cache.set(key, rows, ttl)
    return rows


def _write(action, message: str, label: str):
    """Exécute une écriture ; toute erreur devient une DataError lisible."""
    try:
        return action()
    except Exception as exc:  # noqa: BLE001
        log.error("%s failed: %s", label, exc)
        raise DataError(message) from exc


# ------------------------------------------------------------------- Connexion
def check_connection() -> str:
    """Retourne "OK" ou un message d'erreur lisible."""
    if cache.get("conn_ok"):
        return "OK"
    try:
        _table("members").select("id", count="exact").limit(1).execute()
        cache.set("conn_ok", True, CONN_TTL)
        return "OK"
    except Exception as exc:  # noqa: BLE001
        log.error("Supabase check failed: %s", exc)
        text = str(exc).lower()
        if any(word in text for word in ("fetch", "connect", "resolve", "getaddrinfo")):
            return "Erreur de connexion : l'URL Supabase est injoignable."
        if "jwt" in text or "api key" in text or "permission" in text or "401" in text:
            return "Erreur API : clé Supabase refusée. Utilisez la clé « service_role » (voir README)."
        return "Erreur API : " + (str(exc) or "accès refusé")


# ---------------------------------------------------------------------- Membres
def schema_v3() -> bool:
    """True si la migration 003 (nouveaux champs du profil) est appliquée sur Supabase."""
    known = cache.get("schema_v3")
    if known is not None:
        return known
    try:
        _table("members").select("entry_year,offers,show_phone").limit(1).execute()
        ok = True
    except Exception as exc:  # noqa: BLE001
        log.warning("Migration 003 absente ou illisible : %s", exc)
        ok = False
    cache.set("schema_v3", ok, 600 if ok else 30)
    return ok


def _directory_columns() -> str:
    # Le téléphone sert à l'impression pour les responsables ; les membres ne le voient que si la personne l'autorise.
    columns = LEGACY_COLUMNS + ",phone"
    if schema_v3():
        columns += "," + ",".join(f for f in V3_FIELDS if f != "terms_accepted_at")
    return columns


def _profile_columns() -> str:
    return _directory_columns()


def _only_known(payload: dict) -> dict:
    """Retire les champs de la migration 003 si elle n'est pas encore appliquée (le site reste utilisable)."""
    if schema_v3():
        return payload
    return {k: v for k, v in payload.items() if k not in V3_FIELDS}


def _public(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in {"password", "avatar"}}


def get_members() -> list[dict]:
    """Tous les membres (tous statuts), du plus récent au plus ancien."""
    return _cached_list(
        "members", lambda: _table("members").select(_directory_columns()).order("created_at", desc=True).limit(5000).execute()
    )


def get_active_members() -> list[dict]:
    return [m for m in get_members() if (m.get("status") or "active") == "active"]


def get_member_cached(member_id: str) -> dict | None:
    """Recherche dans la liste en cache (sans appel réseau supplémentaire)."""
    for member in get_members():
        if str(member.get("id")) == str(member_id):
            return member
    return None


def get_member_by_id(member_id: str) -> dict | None:
    try:
        rows = _rows(_table("members").select(_profile_columns()).eq("id", member_id).limit(1).execute())
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch member failed: %s", exc)
        return None


def get_member_by_email(email: str) -> dict | None:
    try:
        for candidate in dict.fromkeys([email.strip(), email.strip().lower()]):
            rows = _rows(_table("members").select(_profile_columns()).eq("email", candidate).limit(1).execute())
            if rows:
                return rows[0]
        return None
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch member by email failed: %s", exc)
        return None


def get_member_avatar(member_id: str) -> str:
    key = "avatar:" + str(member_id)
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        rows = _rows(_table("members").select("avatar").eq("id", member_id).limit(1).execute())
        avatar = (rows[0].get("avatar") or "") if rows else ""
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch avatar failed: %s", exc)
        return ""
    cache.set(key, avatar, AVATAR_TTL)
    return avatar


def _verify_password(stored: str, supplied: str) -> tuple[bool, bool]:
    """Retourne (ok, ancien_format_en_clair)."""
    if not stored:
        return False, False
    try:
        identify_hasher(stored)
    except ValueError:
        # Ancien compte : mot de passe stocké en clair par l'ancienne application.
        return hmac.compare_digest(stored.encode("utf-8"), supplied.encode("utf-8")), True
    return check_password(supplied, stored), False


def authenticate(email: str, password: str) -> dict | None:
    email = (email or "").strip()
    if not email or not password:
        return None
    try:
        row = None
        for candidate in dict.fromkeys([email, email.lower()]):
            rows = _rows(_table("members").select("*").eq("email", candidate).limit(1).execute())
            if rows:
                row = rows[0]
                break
        if not row:
            return None
        ok, legacy = _verify_password(row.get("password") or "", password)
        if not ok:
            return None
        if legacy:
            try:
                _table("members").update({"password": make_password(password)}).eq("id", row["id"]).execute()
            except Exception as exc:  # noqa: BLE001
                log.warning("Password upgrade failed for %s: %s", row.get("id"), exc)
        return _public(row)
    except Exception as exc:  # noqa: BLE001
        log.error("Login failed: %s", exc)
        return None


def create_member(data: dict, password_hash: str, status: str = "active") -> dict:
    """Crée un membre. Lève DataError si l'email existe déjà ou si l'écriture échoue."""
    email = data["email"].strip().lower()
    if get_member_by_email(email):
        raise DataError("Un compte existe déjà avec cet email.")
    payload = {k: v for k, v in data.items() if k in EDITABLE_FIELDS}
    payload.update({"email": email, "password": password_hash, "status": status})
    rows = _rows(_write(lambda: _table("members").insert(_only_known(payload)).execute(),
                        "Erreur lors de la sauvegarde du profil.", "Create member"))
    if not rows:
        raise DataError("Erreur lors de la sauvegarde du profil.")
    cache.delete("members")
    return _public(rows[0])


def update_member(member_id: str, fields: dict) -> dict | None:
    payload = _only_known({k: v for k, v in fields.items() if k in EDITABLE_FIELDS})
    if not payload:
        return get_member_by_id(member_id)
    rows = _rows(_write(lambda: _table("members").update(payload).eq("id", member_id).execute(),
                        "Erreur lors de la sauvegarde.", "Update member"))
    cache.delete_many(["members", "avatar:" + str(member_id)])
    return _public(rows[0]) if rows else None


def admin_update_member(member_id: str, fields: dict) -> None:
    """Rôle et statut : réservé aux responsables (jamais exposé au formulaire de profil)."""
    payload = {k: v for k, v in fields.items() if k in ADMIN_FIELDS}
    _write(lambda: _table("members").update(payload).eq("id", member_id).execute(),
           "Impossible de modifier ce membre.", "Admin update member")
    cache.delete("members")


def set_password(member_id: str, password_hash: str) -> None:
    _write(lambda: _table("members").update({"password": password_hash}).eq("id", member_id).execute(),
           "Impossible de modifier le mot de passe.", "Set password")


def delete_member(member_id: str) -> None:
    _write(lambda: _table("members").delete().eq("id", member_id).execute(),
           "Impossible de supprimer ce membre.", "Delete member")
    cache.delete_many(["members", "avatar:" + str(member_id)])


# ------------------------------------------------------------------- Actualités
def get_news() -> list[dict]:
    return _cached_list("news", lambda: _table("news").select("*").order("created_at", desc=True).limit(100).execute())


def add_news(title: str, desc: str, img: str, date_label: str) -> None:
    _write(lambda: _table("news").insert({"title": title, "desc": desc, "img": img, "date": date_label}).execute(),
           "Impossible de publier l'actualité.", "Add news")
    cache.delete("news")


def update_news(news_id: str, title: str, desc: str, img: str) -> None:
    _write(lambda: _table("news").update({"title": title, "desc": desc, "img": img}).eq("id", news_id).execute(),
           "Impossible de modifier l'actualité.", "Update news")
    cache.delete("news")


def delete_news(news_id: str) -> None:
    _write(lambda: _table("news").delete().eq("id", news_id).execute(),
           "Impossible de supprimer l'actualité.", "Delete news")
    cache.delete("news")


# ----------------------------------------------------------------------- Emplois
def get_jobs() -> list[dict]:
    """Toutes les offres (y compris en attente et expirées) : pour les responsables."""
    return _cached_list("jobs", lambda: _table("jobs").select("*").order("created_at", desc=True).limit(300).execute())


def get_public_jobs() -> list[dict]:
    """Offres validées et non expirées : pour les membres."""
    today = date.today().isoformat()
    return [
        j for j in get_jobs()
        if (j.get("status") or "approved") == "approved" and (not j.get("expires_at") or str(j["expires_at"]) >= today)
    ]


def add_job(title: str, company: str, location: str, salary: str, job_type: str, *,
            apply_contact: str = "", expires_at: str | None = None,
            status: str = "approved", posted_by: str = "") -> None:
    payload = {
        "title": title, "company": company, "location": location, "salary": salary, "type": job_type,
        "apply_contact": apply_contact, "expires_at": expires_at or None, "status": status, "posted_by": posted_by,
    }
    _write(lambda: _table("jobs").insert(payload).execute(), "Impossible d'ajouter l'offre.", "Add job")
    cache.delete("jobs")


def update_job(job_id: str, fields: dict) -> None:
    allowed = {"title", "company", "location", "salary", "type", "apply_contact", "expires_at", "status"}
    payload = {k: (v or None) if k == "expires_at" else v for k, v in fields.items() if k in allowed}
    _write(lambda: _table("jobs").update(payload).eq("id", job_id).execute(),
           "Impossible de modifier l'offre.", "Update job")
    cache.delete("jobs")


def delete_job(job_id: str) -> None:
    _write(lambda: _table("jobs").delete().eq("id", job_id).execute(),
           "Impossible de supprimer l'offre.", "Delete job")
    cache.delete("jobs")


# --------------------------------------------------------------- Fil : likes & commentaires
def get_likes() -> list[dict]:
    try:
        return _rows(_table("post_likes").select("post_type,post_id,member_id").limit(20000).execute())
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch likes failed: %s", exc)
        return []


def toggle_like(post_type: str, post_id: str, member_id: str) -> bool:
    """Ajoute ou retire le « J'aime » d'un membre sur une publication. Retourne True si désormais aimé."""
    existing = _rows(_table("post_likes").select("id").eq("post_type", post_type).eq("post_id", post_id)
                      .eq("member_id", member_id).limit(1).execute())

    def action():
        if existing:
            return _table("post_likes").delete().eq("id", existing[0]["id"]).execute()
        return _table("post_likes").insert(
            {"post_type": post_type, "post_id": post_id, "member_id": member_id}).execute()

    _write(action, "Impossible d'enregistrer votre réaction.", "Toggle like")
    return not existing


def get_comment_counts() -> dict[str, int]:
    try:
        rows = _rows(_table("post_comments").select("post_type,post_id").limit(20000).execute())
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch comment counts failed: %s", exc)
        return {}
    counts: dict[str, int] = {}
    for row in rows:
        key = f"{row['post_type']}:{row['post_id']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def get_comments(post_type: str, post_id: str) -> list[dict]:
    try:
        return _rows(_table("post_comments").select("*").eq("post_type", post_type).eq("post_id", post_id)
                      .order("created_at").limit(500).execute())
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch comments failed: %s", exc)
        return []


def get_comment(comment_id: str) -> dict | None:
    try:
        rows = _rows(_table("post_comments").select("*").eq("id", comment_id).limit(1).execute())
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch comment failed: %s", exc)
        return None


def add_comment(post_type: str, post_id: str, member_id: str, body: str) -> dict:
    payload = {"post_type": post_type, "post_id": post_id, "member_id": member_id, "body": body}
    response = _write(lambda: _table("post_comments").insert(payload).execute(),
                       "Impossible d'ajouter le commentaire.", "Add comment")
    rows = _rows(response)
    if not rows:
        raise DataError("Impossible d'ajouter le commentaire.")
    return rows[0]


def delete_comment(comment_id: str) -> None:
    _write(lambda: _table("post_comments").delete().eq("id", comment_id).execute(),
           "Impossible de supprimer le commentaire.", "Delete comment")


# --------------------------------------------------------------------- Événements
def get_events() -> list[dict]:
    return _cached_list("events", lambda: _table("events").select("*").order("starts_at").limit(300).execute())


def add_event(title: str, description: str, location: str, starts_at: str) -> None:
    payload = {"title": title, "description": description, "location": location, "starts_at": starts_at}
    _write(lambda: _table("events").insert(payload).execute(), "Impossible de créer l'événement.", "Add event")
    cache.delete("events")


def delete_event(event_id: str) -> None:
    _write(lambda: _table("events").delete().eq("id", event_id).execute(),
           "Impossible de supprimer l'événement.", "Delete event")
    cache.delete("events")


def get_rsvps() -> list[dict]:
    try:
        return _rows(_table("event_rsvps").select("event_id,member_id").limit(10000).execute())
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch rsvps failed: %s", exc)
        return []


def set_rsvp(event_id: str, member_id: str, going: bool) -> None:
    def action():
        if going:
            return _table("event_rsvps").upsert(
                {"event_id": event_id, "member_id": member_id}, on_conflict="event_id,member_id").execute()
        return _table("event_rsvps").delete().eq("event_id", event_id).eq("member_id", member_id).execute()
    _write(action, "Impossible d'enregistrer votre réponse.", "Set rsvp")


# -------------------------------------------------------------------- Cotisations
def get_dues(year: int | None = None) -> list[dict]:
    try:
        query = _table("dues").select("*")
        if year is not None:
            query = query.eq("year", year)
        return _rows(query.order("created_at", desc=True).limit(10000).execute())
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch dues failed: %s", exc)
        return []


def get_member_dues(member_id: str) -> list[dict]:
    try:
        return _rows(_table("dues").select("*").eq("member_id", member_id).order("year", desc=True).execute())
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch member dues failed: %s", exc)
        return []


def get_due(due_id: str) -> dict | None:
    try:
        rows = _rows(_table("dues").select("*").eq("id", due_id).limit(1).execute())
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch due failed: %s", exc)
        return None


def get_due_by_reference(reference: str) -> dict | None:
    try:
        rows = _rows(_table("dues").select("*").eq("reference", reference).limit(1).execute())
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch due by reference failed: %s", exc)
        return None


def get_due_rate(year: int) -> int | None:
    """Montant de cotisation défini par les responsables pour l'année, ou None si jamais configuré."""
    try:
        rows = _rows(_table("due_rates").select("amount").eq("year", year).limit(1).execute())
        return int(rows[0]["amount"]) if rows else None
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch due rate failed: %s", exc)
        return None


def set_due_rate(year: int, amount: int) -> None:
    payload = {"year": year, "amount": amount, "updated_at": datetime.now(timezone.utc).isoformat()}
    _write(lambda: _table("due_rates").upsert(payload, on_conflict="year").execute(),
           "Impossible d'enregistrer le montant de la cotisation.", "Set due rate")


def ensure_dues(year: int, amount: int, member_ids: list[str]) -> int:
    """Crée la cotisation de l'année pour chaque membre qui n'en a pas encore. Retourne le nombre créé."""
    existing = {str(d["member_id"]) for d in get_dues(year)}
    missing = [{"member_id": mid, "year": year, "amount": amount} for mid in member_ids if str(mid) not in existing]
    if missing:
        _write(lambda: _table("dues").upsert(missing, on_conflict="member_id,year", ignore_duplicates=True).execute(),
               "Impossible de créer les cotisations.", "Ensure dues")
    return len(missing)


def apply_due_rate(year: int, amount: int, member_ids: list[str]) -> tuple[int, int]:
    """Fixe le montant pour TOUS les membres actifs, sans exception : crée la cotisation des membres qui n'en
    ont pas encore et aligne le montant de celles déjà créées mais pas encore payées sur le nouveau montant.
    Les cotisations déjà marquées payées ne sont jamais modifiées (le paiement reçu reste un fait acquis).
    Retourne (nombre créées, nombre mises à jour)."""
    existing = {str(d["member_id"]): d for d in get_dues(year)}
    created = ensure_dues(year, amount, [mid for mid in member_ids if str(mid) not in existing])
    to_update = [d["id"] for d in existing.values() if d["status"] != "paid" and int(d["amount"]) != amount]
    if to_update:
        _write(lambda: _table("dues").update({"amount": amount}).in_("id", to_update).execute(),
               "Impossible de mettre à jour le montant des cotisations.", "Update due amounts")
    return created, len(to_update)


def get_or_create_due(member_id: str, year: int, amount: int) -> dict | None:
    for due in get_member_dues(member_id):
        if due["year"] == year:
            return due
    ensure_dues(year, amount, [member_id])
    for due in get_member_dues(member_id):
        if due["year"] == year:
            return due
    return None


def set_due_reference(due_id: str, reference: str) -> None:
    _write(lambda: _table("dues").update({"reference": reference, "method": "cinetpay"}).eq("id", due_id).execute(),
           "Impossible de préparer le paiement.", "Set due reference")


def mark_due_paid(due_id: str, method: str) -> None:
    payload = {"status": "paid", "method": method, "paid_at": datetime.now(timezone.utc).isoformat()}
    _write(lambda: _table("dues").update(payload).eq("id", due_id).execute(),
           "Impossible d'enregistrer le paiement.", "Mark due paid")


def mark_due_pending(due_id: str) -> None:
    _write(lambda: _table("dues").update({"status": "pending", "paid_at": None}).eq("id", due_id).execute(),
           "Impossible de modifier la cotisation.", "Mark due pending")


# ------------------------------------------------------------------------ Galerie
def get_photos() -> list[dict]:
    return _cached_list("photos", lambda: _table("photos").select("*").order("created_at", desc=True).limit(500).execute())


def get_photo(photo_id: str) -> dict | None:
    for photo in get_photos():
        if str(photo["id"]) == str(photo_id):
            return photo
    return None


def add_photo(album: str, title: str, url: str, path: str, uploaded_by: str) -> None:
    payload = {"album": album, "title": title, "url": url, "path": path, "uploaded_by": uploaded_by}
    _write(lambda: _table("photos").insert(payload).execute(), "Impossible d'enregistrer la photo.", "Add photo")
    cache.delete("photos")


def delete_photo(photo_id: str) -> None:
    _write(lambda: _table("photos").delete().eq("id", photo_id).execute(),
           "Impossible de supprimer la photo.", "Delete photo")
    cache.delete("photos")


# ---------------------------------------------------------------------- Messages
def is_group(identifier: str) -> bool:
    return (identifier or "").startswith(GROUP_PREFIX)


def get_user_messages(email: str, limit: int = 400) -> list[dict]:
    """Derniers messages privés envoyés ou reçus par `email` (du plus ancien au plus récent)."""
    email = _safe(email)
    try:
        res = (
            _table("messages").select(MESSAGE_COLUMNS)
            .or_(f"sender_id.eq.{email},receiver_id.eq.{email}")
            .order("created_at", desc=True).limit(limit).execute()
        )
        return [m for m in reversed(_rows(res)) if not is_group(m["receiver_id"])]
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch messages failed: %s", exc)
        return []


def get_contact_summaries(email: str) -> dict[str, dict]:
    """{interlocuteur: {last_text, last_time, last_at, unread}} en une seule requête SQL (RPC)."""
    email = _safe(email)
    try:
        rows = _rows(get_client().rpc("conversation_summaries", {"me": email}).execute())
        return {r["peer"]: r for r in rows}
    except Exception as exc:  # noqa: BLE001
        log.warning("RPC conversation_summaries indisponible (%s) : calcul de secours.", exc)
    summaries: dict[str, dict] = {}
    for msg in get_user_messages(email):
        other = msg["receiver_id"] if msg["sender_id"] == email else msg["sender_id"]
        entry = summaries.setdefault(other, {"peer": other, "unread": 0})
        entry.update(last_text=msg["text"], last_time=msg["time"], last_at=msg["created_at"])
        if msg["receiver_id"] == email and not msg.get("is_read"):
            entry["unread"] += 1
    return summaries


def get_conversation(me: str, other: str, after: str | None = None, limit: int = 500) -> list[dict]:
    me, other = _safe(me), _safe(other)
    pair = f"and(sender_id.eq.{me},receiver_id.eq.{other}),and(sender_id.eq.{other},receiver_id.eq.{me})"
    try:
        query = _table("messages").select(MESSAGE_COLUMNS).or_(pair)
        if after:
            return _rows(query.gt("created_at", after).order("created_at", desc=False).limit(limit).execute())
        return list(reversed(_rows(query.order("created_at", desc=True).limit(limit).execute())))
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch conversation failed: %s", exc)
        return []


def get_group_conversation(room: str, after: str | None = None, limit: int = 300) -> list[dict]:
    room = _safe(room)
    try:
        query = _table("messages").select(MESSAGE_COLUMNS).eq("receiver_id", room)
        if after:
            return _rows(query.gt("created_at", after).order("created_at", desc=False).limit(limit).execute())
        return list(reversed(_rows(query.order("created_at", desc=True).limit(limit).execute())))
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch group conversation failed: %s", exc)
        return []


def get_group_last(room: str) -> dict | None:
    try:
        rows = _rows(_table("messages").select(MESSAGE_COLUMNS).eq("receiver_id", _safe(room))
                     .order("created_at", desc=True).limit(1).execute())
        return rows[0] if rows else None
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch group last failed: %s", exc)
        return None


def save_message(sender: str, receiver: str, text: str, time_label: str) -> dict:
    _safe(sender), _safe(receiver)  # lève ValueError si l'adresse est suspecte
    payload = {"sender_id": sender, "receiver_id": receiver, "text": text, "time": time_label, "is_read": False}
    rows = _rows(_write(lambda: _table("messages").insert(payload).execute(),
                        "Le message n'a pas pu être envoyé.", "Save message"))
    if not rows:
        raise DataError("Le message n'a pas pu être envoyé.")
    return rows[0]


def mark_as_read(me: str, contact: str) -> None:
    try:
        (_table("messages").update({"is_read": True})
         .eq("receiver_id", me).eq("sender_id", contact).eq("is_read", False).execute())
    except Exception as exc:  # noqa: BLE001
        log.error("Mark as read failed: %s", exc)


def get_unread_count(email: str) -> int:
    try:
        res = (_table("messages").select("id", count="exact")
               .eq("receiver_id", email).eq("is_read", False).limit(1).execute())
        return int(res.count or 0)
    except Exception as exc:  # noqa: BLE001
        log.error("Unread count failed: %s", exc)
        return 0


def get_unnotified_messages(before_iso: str) -> list[dict]:
    """Messages privés non lus, plus anciens que `before_iso`, pour lesquels aucun e-mail n'a été envoyé."""
    try:
        rows = _rows(_table("messages").select("id,sender_id,receiver_id,created_at")
                     .eq("is_read", False).eq("notified", False).lt("created_at", before_iso)
                     .order("created_at").limit(2000).execute())
        return [m for m in rows if not is_group(m["receiver_id"])]
    except Exception as exc:  # noqa: BLE001
        log.error("Fetch unnotified failed: %s", exc)
        return []


def mark_notified(message_ids: list[str]) -> None:
    if message_ids:
        _write(lambda: _table("messages").update({"notified": True}).in_("id", message_ids).execute(),
               "Impossible de marquer les messages.", "Mark notified")
