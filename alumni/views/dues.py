"""Cotisations : suivi par membre et paiement en ligne (CinetPay)."""
import logging
import uuid

from django.conf import settings
from django.contrib import messages as flash
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .. import data_service as ds
from .. import payments, ratelimit
from ..decorators import member_required
from ._common import external_url, session_member

log = logging.getLogger(__name__)


def settle_due(due: dict) -> str:
    """Vérifie auprès de CinetPay et marque la cotisation payée si le paiement est accepté. Retourne le statut."""
    reference = due.get("reference")
    if not reference:
        return "UNKNOWN"
    result = payments.check_payment(reference)
    if result["status"] == "ACCEPTED":
        if result["amount"] and result["amount"] != int(due["amount"]):
            log.error("Montant inattendu pour %s : %s au lieu de %s", reference, result["amount"], due["amount"])
            return "AMOUNT_MISMATCH"
        ds.mark_due_paid(due["id"], result["method"] or "cinetpay")
    return result["status"]


@member_required
def dues_page(request):
    me = session_member(request)["id"]
    year = timezone.localdate().year
    amount = ds.get_due_rate(year) or settings.DUES_AMOUNT
    try:
        current = ds.get_or_create_due(me, year, amount)
    except ds.DataError as exc:
        flash.error(request, str(exc))
        current = None
    return render(request, "alumni/dues.html", {
        "current": current,
        "history": [d for d in ds.get_member_dues(me) if not current or d["id"] != current["id"]],
        "year": year,
        "online": payments.configured(),
        "currency": settings.DUES_CURRENCY,
        "instructions": settings.PAYMENT_INSTRUCTIONS,
    })


@member_required
@require_POST
def dues_pay(request, due_id):
    me = session_member(request)
    due = ds.get_due(due_id)
    if not due or str(due["member_id"]) != me["id"]:
        flash.error(request, "Cotisation introuvable.")
    elif due["status"] == "paid":
        flash.info(request, "Cette cotisation est déjà réglée. Merci !")
    elif not ratelimit.hit("pay", me["id"], 10, 600):
        flash.error(request, ratelimit.TOO_MANY)
    else:
        member = ds.get_member_by_id(me["id"]) or {}
        transaction_id = f"AEPS{uuid.uuid4().hex[:20]}"
        try:
            ds.set_due_reference(due["id"], transaction_id)
            url = payments.init_payment(
                transaction_id=transaction_id, amount=int(due["amount"]),
                description=f"Cotisation AEPS-ALUMNI {due['year']}", member=member,
                notify_url=external_url(reverse("dues_notify")),
                return_url=external_url(reverse("dues_return")) + f"?due={due['id']}",
            )
        except (payments.PaymentError, ds.DataError) as exc:
            flash.error(request, str(exc))
        else:
            return redirect(url)
    return redirect("dues")


@member_required
@require_GET
def dues_return(request):
    """Le membre revient de la page de paiement : on vérifie le résultat auprès de CinetPay."""
    due = ds.get_due(request.GET.get("due", ""))
    if not due or str(due["member_id"]) != session_member(request)["id"]:
        return redirect("dues")
    if due["status"] != "paid":
        try:
            status = settle_due(due)
        except payments.PaymentError as exc:
            flash.error(request, str(exc))
            return redirect("dues")
        if status == "ACCEPTED":
            flash.success(request, "Paiement reçu. Merci pour votre cotisation !")
        elif status in ("WAITING", "WAITING_FOR_CUSTOMER", "PENDING"):
            flash.info(request, "Paiement en attente de confirmation de votre opérateur. Actualisez dans un instant.")
        else:
            flash.error(request, "Le paiement n'a pas abouti. Vous pouvez réessayer.")
    else:
        flash.success(request, "Cotisation réglée. Merci !")
    return redirect("dues")


@csrf_exempt
def dues_notify(request):
    """Notification serveur de CinetPay. Répond toujours 200 ; ne croit jamais le contenu reçu : vérifie via l'API."""
    if request.method == "POST":
        reference = request.POST.get("cpm_trans_id", "").strip()
        site_id = request.POST.get("cpm_site_id", "").strip()
        due = ds.get_due_by_reference(reference) if reference and site_id == settings.CINETPAY_SITE_ID else None
        if due and due["status"] != "paid":
            try:
                settle_due(due)
            except payments.PaymentError as exc:
                log.error("Notification CinetPay non traitée : %s", exc)
    return HttpResponse("OK")
