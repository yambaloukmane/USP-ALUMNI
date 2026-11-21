"""Champs du profil : listes de choix et validation, partagées par l'inscription et la page profil."""
import re

COUNTRIES = [
    "Côte d'Ivoire", "Burkina Faso", "Mali", "Sénégal", "Guinée", "Bénin", "Togo", "Niger", "Ghana", "Nigeria",
    "Cameroun", "Gabon", "Congo", "RD Congo", "Tchad", "Mauritanie", "Maroc", "Algérie", "Tunisie", "Égypte",
    "Rwanda", "Madagascar", "Afrique du Sud", "France", "Belgique", "Suisse", "Luxembourg", "Allemagne",
    "Royaume-Uni", "Italie", "Espagne", "Portugal", "Pays-Bas", "Russie", "Canada", "États-Unis", "Brésil",
    "Chine", "Inde", "Japon", "Émirats arabes unis", "Qatar", "Arabie saoudite", "Autre pays",
]
SITUATIONS = ["Étudiant", "En emploi", "En recherche d'emploi", "Entrepreneur", "Autre"]
SCHOOL_OTHER = "Autre école (préciser)"
SCHOOL_NONE = "Pas encore intégré"
SCHOOLS = ["INP-HB (Yamoussoukro)", "ESATIC (Abidjan)", "Université Félix Houphouët-Boigny", SCHOOL_OTHER, SCHOOL_NONE]
SECTORS = [
    "Informatique et numérique", "Télécommunications", "BTP et génie civil", "Énergie", "Mines et pétrole",
    "Industrie et mécanique", "Électronique et automatisme", "Agriculture et agroalimentaire", "Finance et banque",
    "Santé", "Enseignement et recherche", "Conseil", "Commerce et distribution", "Transport et logistique",
    "Administration publique", "Autre",
]
OFFERS = [("mentorat", "Mentorat (accompagner des étudiants)"), ("stages", "Stages"),
          ("emplois", "Offres d'emploi"), ("orientation", "Conseils d'orientation")]
SEEKS = [("stage", "Un stage"), ("emploi", "Un emploi"), ("mentor", "Un mentor"), ("partenaires", "Des partenaires")]
OFFER_LABELS, SEEK_LABELS = dict(OFFERS), dict(SEEKS)
TRACK_SUGGESTIONS = ["Maths-Physique", "Physique-Chimie", "Physique-Technologie", "Sciences de l'ingénieur"]

BIO_MAX = 300
PASSWORD_MIN_LENGTH = 8
_YEAR = re.compile(r"^(19|20)\d{2}$")

STEP_ACCOUNT, STEP_PREPA, STEP_SITUATION, STEP_NETWORK = 1, 2, 3, 4


def with_current(options: list[str], current: str | None) -> list[str]:
    """Ajoute la valeur déjà enregistrée si elle n'est pas dans la liste (anciens profils en texte libre)."""
    current = (current or "").strip()
    return options + [current] if current and current not in options and current not in ("Non défini", "Non définie") else options


def _text(post, key: str, limit: int) -> str:
    return " ".join(post.get(key, "").split())[:limit]


def _choices(post, key: str, allowed: dict) -> list[str]:
    return [v for v in post.getlist(key) if v in allowed]


def parse_profile(post, registration: bool) -> tuple[dict, str, int]:
    """Lit et valide le formulaire. Retourne (données, message d'erreur, étape concernée par l'erreur)."""
    school = _text(post, "school", 100)
    if school == SCHOOL_OTHER:
        school = _text(post, "school_other", 100) or "Autre école"
    offers = _choices(post, "offers", OFFER_LABELS)
    data = {
        "first_name": _text(post, "first_name", 80), "last_name": _text(post, "last_name", 80),
        "phone": _text(post, "phone", 30), "phone_whatsapp": post.get("phone_whatsapp") == "on",
        "promo": _text(post, "promo", 10), "entry_year": _text(post, "entry_year", 10),
        "track": _text(post, "track", 80), "school": school, "school_track": _text(post, "school_track", 100),
        "referent": _text(post, "referent", 120),
        "situation": _text(post, "situation", 40), "job": _text(post, "job", 120), "company": _text(post, "company", 120),
        "sector": _text(post, "sector", 100), "city": _text(post, "city", 80), "country": _text(post, "country", 80),
        "offers": offers, "seeks": _choices(post, "seeks", SEEK_LABELS), "is_mentor": "mentorat" in offers,
        "linkedin": post.get("linkedin", "").strip()[:300], "bio": post.get("bio", "").strip()[:BIO_MAX],
        "show_email": post.get("show_email") == "on", "show_phone": post.get("show_phone") == "on",
    }

    def fail(message: str, step: int):
        return data, message, step

    if not data["first_name"] or not data["last_name"]:
        return fail("Indiquez votre prénom et votre nom.", STEP_ACCOUNT)
    if registration and not data["phone"]:
        return fail("Indiquez votre numéro de téléphone.", STEP_ACCOUNT)
    if data["phone"] and not re.fullmatch(r"[+\d][\d\s().-]{5,28}", data["phone"]):
        return fail("Le numéro de téléphone n'est pas valide (ex : +225 07 00 00 00 00).", STEP_ACCOUNT)
    if not _YEAR.match(data["promo"]):
        return fail("L'année de promotion doit comporter 4 chiffres (ex : 2020).", STEP_PREPA)
    if data["entry_year"] and not _YEAR.match(data["entry_year"]):
        return fail("L'année d'entrée à la Prépa doit comporter 4 chiffres (ex : 2018).", STEP_PREPA)
    if data["entry_year"] and int(data["entry_year"]) > int(data["promo"]):
        return fail("L'année d'entrée ne peut pas être après l'année de promotion.", STEP_PREPA)
    if data["school"] == SCHOOL_NONE:
        data["school_track"] = ""
    if registration and data["situation"] not in SITUATIONS:
        return fail("Choisissez votre situation actuelle.", STEP_SITUATION)
    if data["situation"] and data["situation"] not in SITUATIONS:
        data["situation"] = ""
    if registration and not data["country"]:
        return fail("Choisissez votre pays de résidence.", STEP_SITUATION)
    if data["linkedin"] and not data["linkedin"].startswith("https://"):
        return fail("Le lien LinkedIn doit commencer par https://", STEP_NETWORK)
    if registration and post.get("terms") != "on":
        return fail("Vous devez accepter les conditions d'utilisation.", STEP_NETWORK)
    return data, "", 0


def form_values(data: dict | None) -> dict:
    """Valeurs à réafficher dans le formulaire (l'école hors liste repasse par « Autre école »)."""
    values = dict(data or {})
    school = values.get("school") or ""
    if school and school not in SCHOOLS:
        values["school_other"] = "" if school == "Autre école" else school
        values["school"] = SCHOOL_OTHER
    values.setdefault("offers", [])
    values.setdefault("seeks", [])
    return values


def choice_context(values: dict) -> dict:
    """Listes de choix pour les menus déroulants et cases à cocher."""
    return {
        "countries": with_current(COUNTRIES, values.get("country")),
        "sectors": with_current(SECTORS, values.get("sector")),
        "schools": SCHOOLS, "school_other_label": SCHOOL_OTHER, "school_none_label": SCHOOL_NONE,
        "situations": SITUATIONS, "offer_choices": OFFERS, "seek_choices": SEEKS,
        "track_suggestions": TRACK_SUGGESTIONS, "bio_max": BIO_MAX, "password_min": PASSWORD_MIN_LENGTH,
    }
