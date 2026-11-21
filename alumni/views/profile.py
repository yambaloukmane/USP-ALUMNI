"""Profil du membre et photos de profil."""
import base64
import logging
import time
import uuid

from django.conf import settings
from django.contrib import messages as flash
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .. import data_service as ds
from .. import storage
from ..decorators import member_required
from ..images import compress_jpeg
from ..profile_form import choice_context, form_values, parse_profile
from ._common import MAX_UPLOAD_BYTES, session_member

log = logging.getLogger(__name__)

@member_required
@require_http_methods(["GET", "POST"])
def profile(request):
    current = session_member(request)
    member = ds.get_member_by_id(current["id"])
    if not member:
        request.session.flush()
        flash.error(request, "Ce compte n'existe plus.")
        return redirect("login")

    if request.method == "POST":
        fields, problem, _step = parse_profile(request.POST, registration=False)
        fields.pop("referent", None)  # saisi à l'inscription uniquement : ne pas l'effacer ici
        if problem:
            flash.error(request, problem)
            values = form_values({**member, **fields, "school_other": request.POST.get("school_other", "")})
            return render(request, "alumni/profile.html", {"member": member, "f": values, **choice_context(values)})
        try:
            saved = ds.update_member(member["id"], fields)
        except ds.DataError as exc:
            flash.error(request, str(exc))
        else:
            if saved:
                request.session["member"] = {
                    **current,
                    "first_name": saved.get("first_name") or "",
                    "last_name": saved.get("last_name") or "",
                }
                flash.success(request, "Profil mis à jour !")
            else:
                flash.error(request, "Erreur lors de la sauvegarde.")
        return redirect("profile")

    values = form_values(member)
    return render(request, "alumni/profile.html", {"member": member, "f": values, **choice_context(values)})


@member_required
@require_POST
def profile_avatar(request):
    uploaded = request.FILES.get("avatar")
    if not uploaded:
        flash.error(request, "Aucune image sélectionnée.")
        return redirect("profile")
    if uploaded.size > MAX_UPLOAD_BYTES:
        flash.error(request, "Image trop volumineuse (8 Mo maximum).")
        return redirect("profile")
    try:
        jpeg = compress_jpeg(uploaded, 400, 75)
    except Exception as exc:  # noqa: BLE001 - fichier illisible ou non image
        log.info("Avatar rejected: %s", exc)
        flash.error(request, "Erreur lors du traitement de l'image.")
        return redirect("profile")

    member_id = session_member(request)["id"]
    old = ds.get_member_avatar(member_id)
    try:
        value = storage.upload(settings.BUCKET_AVATARS, f"{member_id}/{uuid.uuid4().hex}.jpg", jpeg, "image/jpeg")
    except storage.StorageError:
        # Secours : l'ancien système (image dans la base) garde la fonction disponible.
        value = "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")
    try:
        ds.update_member(member_id, {"avatar": value})
    except ds.DataError:
        flash.error(request, "Erreur lors de la mise à jour.")
        return redirect("profile")

    old_path = storage.path_from_url(settings.BUCKET_AVATARS, old)
    if old_path:
        storage.remove(settings.BUCKET_AVATARS, old_path)
    request.session["avatar_v"] = int(time.time())
    flash.success(request, "Photo mise à jour !")
    return redirect("profile")


@member_required
@require_GET
def avatar_image(request, member_id):
    avatar = ds.get_member_avatar(member_id)
    if avatar.startswith("data:image/"):
        try:
            header, encoded = avatar.split(",", 1)
            response = HttpResponse(base64.b64decode(encoded), content_type=header[5:].split(";")[0])
        except (ValueError, base64.binascii.Error):
            raise Http404("Avatar illisible")
    elif avatar.startswith("https://"):
        response = HttpResponseRedirect(avatar)
    else:
        raise Http404("Pas d'avatar")
    response["Cache-Control"] = "private, max-age=300"
    return response
