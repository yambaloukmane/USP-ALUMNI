"""Pages publiques, formulaire de contact, fichiers PWA."""
import json
import logging

from django.conf import settings
from django.contrib import messages as flash
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.views.decorators.http import require_GET, require_http_methods

from .. import data_service as ds
from .. import ratelimit
from ._common import external_url, valid_email

log = logging.getLogger(__name__)


def home(request):
    members = ds.get_active_members()
    stats = {
        "members": len(members),
        "promos": len({m.get("promo") for m in members if m.get("promo")}),
        "mentors": sum(1 for m in members if m.get("is_mentor")),
        "jobs": len(ds.get_public_jobs()),
    }
    return render(request, "alumni/home.html", {"stats": stats if stats["members"] else None})


def about(request):
    return render(request, "alumni/about.html")


def services(request):
    return render(request, "alumni/services.html")


def treasury(request):
    return render(request, "alumni/treasury.html")


def offline(request):
    return render(request, "alumni/offline.html")


@require_http_methods(["GET", "POST"])
def contact(request):
    form = {"name": "", "email": "", "message": ""}
    if request.method == "POST":
        form = {k: request.POST.get(k, "").strip() for k in form}
        if not ratelimit.hit("contact", ratelimit.client_ip(request), 5, 3600):
            flash.error(request, ratelimit.TOO_MANY)
        elif not all(form.values()):
            flash.error(request, "Veuillez remplir tous les champs.")
        elif not valid_email(form["email"]):
            flash.error(request, "Veuillez entrer une adresse email valide.")
        elif len(form["message"]) > 5000 or len(form["name"]) > 120:
            flash.error(request, "Message ou nom trop long.")
        else:
            try:
                EmailMessage(
                    subject=f"[AEPS-ALUMNI] Message de {form['name'][:80]}",
                    body=f"De : {form['name']} <{form['email']}>\n\n{form['message']}",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[settings.CONTACT_EMAIL],
                    reply_to=[form["email"]],  # « Répondre » écrit directement à la personne
                ).send()
            except Exception as exc:  # noqa: BLE001
                log.error("Contact mail failed: %s", exc)
                flash.error(request, "Le message n'a pas pu être envoyé. Réessayez plus tard.")
            else:
                flash.success(request, "Merci ! Votre message a bien été envoyé.")
                return redirect("contact")
    return render(request, "alumni/contact.html", {"form": form})


# ------------------------------------------------------------ Application installable (PWA)
@require_GET
def manifest(request):
    data = {
        "name": "AEPS-ALUMNI",
        "short_name": "AEPS-ALUMNI",
        "description": "Le réseau des anciens élèves de la Prépa de San-Pédro.",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#38bdf8",
        "lang": "fr",
        "icons": [
            {"src": static("alumni/icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("alumni/icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": static("alumni/icons/icon-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return HttpResponse(json.dumps(data), content_type="application/manifest+json")


@require_GET
def service_worker(request):
    path = settings.BASE_DIR / "alumni" / "static" / "alumni" / "sw.js"
    response = HttpResponse(path.read_text(encoding="utf-8"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


# ------------------------------------------------------------ Référencement (SEO)
# Pages publiques indexables : (chemin, nom de route, fréquence de mise à jour, priorité)
PUBLIC_PAGES = [
    ("/", "home", "weekly", "1.0"),
    ("/about/", "about", "monthly", "0.6"),
    ("/services/", "services", "monthly", "0.6"),
    ("/treasury/", "treasury", "monthly", "0.5"),
    ("/contact/", "contact", "monthly", "0.5"),
]


@require_GET
def robots_txt(request):
    disallow = [
        "/login/", "/register/", "/forgot/", "/profile/", "/bienvenue/", "/avatar/",
        "/feed/", "/jobs/propose/", "/members/", "/events/", "/gallery/", "/cotisations/",
        "/messages/", "/responsable/", "/offline/", "/manifest.webmanifest", "/sw.js",
    ]
    lines = ["User-agent: *"] + [f"Disallow: {path}" for path in disallow] + [
        "", f"Sitemap: {external_url('/sitemap.xml')}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


@require_GET
def sitemap_xml(request):
    urls = "".join(
        f"<url><loc>{external_url(path)}</loc><changefreq>{freq}</changefreq><priority>{prio}</priority></url>"
        for path, _name, freq, prio in PUBLIC_PAGES
    )
    xml = f'<?xml version="1.0" encoding="UTF-8"?>' \
          f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return HttpResponse(xml, content_type="application/xml")


__all__ = ["home", "about", "services", "treasury", "offline", "contact", "manifest", "service_worker",
           "robots_txt", "sitemap_xml"]
