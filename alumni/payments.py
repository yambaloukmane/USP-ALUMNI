"""Paiement Mobile Money / carte via CinetPay (https://docs.cinetpay.com).

Flux : initialisation -> le membre paie sur la page CinetPay -> notification serveur (notify_url)
et/ou retour du membre (return_url) -> on vérifie TOUJOURS le statut auprès de CinetPay avant
de marquer une cotisation comme payée (la notification seule n'est jamais crue).
"""
import logging

import httpx
from django.conf import settings

log = logging.getLogger(__name__)

API = "https://api-checkout.cinetpay.com/v2"


class PaymentError(Exception):
    """Erreur lisible côté utilisateur."""


def configured() -> bool:
    return bool(settings.CINETPAY_API_KEY and settings.CINETPAY_SITE_ID)


def _post(path: str, payload: dict) -> dict:
    try:
        response = httpx.post(f"{API}{path}", json=payload, timeout=20,
                              headers={"User-Agent": "AEPS-ALUMNI/1.0"})
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.error("CinetPay %s failed: %s", path, exc)
        raise PaymentError("Le service de paiement est injoignable. Réessayez dans un instant.") from exc


def init_payment(*, transaction_id: str, amount: int, description: str, member: dict,
                 notify_url: str, return_url: str) -> str:
    """Crée la transaction et renvoie l'adresse de la page de paiement."""
    if not configured():
        raise PaymentError("Le paiement en ligne n'est pas configuré.")
    if amount % 5 != 0:
        raise PaymentError("Le montant de la cotisation doit être un multiple de 5.")
    payload = {
        "apikey": settings.CINETPAY_API_KEY,
        "site_id": settings.CINETPAY_SITE_ID,
        "transaction_id": transaction_id,
        "amount": int(amount),
        "currency": settings.DUES_CURRENCY,
        "description": description,
        "notify_url": notify_url,
        "return_url": return_url,
        "channels": "ALL",
        "lang": "fr",
        # Champs obligatoires pour proposer aussi la carte bancaire.
        "customer_id": str(member.get("id", "")),
        "customer_name": member.get("first_name") or "Membre",
        "customer_surname": member.get("last_name") or "AEPS",
        "customer_phone_number": member.get("phone") or "0000000000",
        "customer_email": member.get("email", ""),
        "customer_address": member.get("city") or "Abidjan",
        "customer_city": member.get("city") or "Abidjan",
        "customer_country": "CI",
        "customer_state": "CI",
        "customer_zip_code": "00225",
    }
    data = _post("/payment", payload)
    url = (data.get("data") or {}).get("payment_url")
    if str(data.get("code")) != "201" or not url:
        log.error("CinetPay init refused: %s", {k: data.get(k) for k in ("code", "message", "description")})
        raise PaymentError("Le paiement n'a pas pu être initialisé. Contactez un responsable si cela persiste.")
    return url


def check_payment(transaction_id: str) -> dict:
    """Interroge CinetPay. Retourne {"status": ACCEPTED|REFUSED|WAITING|CANCELLED|UNKNOWN, "amount": int, "method": str}."""
    if not configured():
        raise PaymentError("Le paiement en ligne n'est pas configuré.")
    data = _post("/payment/check", {
        "apikey": settings.CINETPAY_API_KEY,
        "site_id": settings.CINETPAY_SITE_ID,
        "transaction_id": transaction_id,
    })
    info = data.get("data") or {}
    status = str(info.get("status") or "").upper()
    if not status:
        status = "CANCELLED" if str(data.get("code")) == "627" else "UNKNOWN"
    try:
        amount = int(float(info.get("amount") or 0))
    except (TypeError, ValueError):
        amount = 0
    return {"status": status, "amount": amount, "method": str(info.get("payment_method") or "")}
