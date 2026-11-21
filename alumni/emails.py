"""Envoi des e-mails (codes, notifications). Les envois groupés partent en arrière-plan."""
import logging
import threading

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives, send_mail
from django.utils.html import escape

log = logging.getLogger(__name__)

CODE_SUBJECTS = {
    "register": "Votre code de vérification AEPS-ALUMNI",
    "reset": "Réinitialisation de votre mot de passe AEPS-ALUMNI",
}
CODE_INTROS = {
    "register": "Voici votre code de vérification :",
    "reset": "Voici votre code pour réinitialiser votre mot de passe :",
}


def send_code_email(to: str, first_name: str, code: str, purpose: str = "register") -> None:
    """Envoie un code à 6 chiffres. Lève une exception si l'envoi échoue."""
    minutes = settings.REGISTRATION_CODE_TTL_SECONDS // 60
    intro = CODE_INTROS[purpose]
    html = (
        '<div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:24px;'
        'border:1px solid #e5e7eb;border-radius:16px">'
        '<h2 style="color:#0ea5e9;margin:0 0 16px">AEPS-ALUMNI</h2>'
        f"<p>Bonjour {escape(first_name)},</p><p>{intro}</p>"
        '<p style="font-size:34px;font-weight:bold;letter-spacing:8px;text-align:center;'
        f'background:#f0f9ff;border-radius:12px;padding:16px;margin:16px 0">{code}</p>'
        f"<p>Il est valable {minutes} minutes.</p>"
        '<p style="color:#6b7280;font-size:12px">Si vous n\'êtes pas à l\'origine de cette demande, '
        "ignorez ce message.</p></div>"
    )
    send_mail(
        subject=CODE_SUBJECTS[purpose],
        message=(f"Bonjour {first_name},\n\n{intro} {code}\n\nIl est valable {minutes} minutes.\n"
                "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n"),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[to],
        html_message=html,
    )


def _run(work) -> None:
    if settings.NOTIFY_ASYNC:
        threading.Thread(target=work, daemon=True).start()
    else:
        work()


def send_simple(to: str, subject: str, body: str) -> None:
    """Message court à un destinataire, sans bloquer la page ; les erreurs sont seulement journalisées."""
    def work():
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to])
        except Exception as exc:  # noqa: BLE001
            log.error("Email to %s failed: %s", to, exc)

    _run(work)


def notify_members(subject: str, body: str, recipients: list[str]) -> None:
    """Même message à beaucoup de membres, par lots en copie cachée."""
    unique = list(dict.fromkeys(r for r in recipients if r))
    size = max(1, settings.NOTIFY_BATCH_SIZE)

    def work():
        for i in range(0, len(unique), size):
            try:
                EmailMultiAlternatives(
                    subject, body, settings.DEFAULT_FROM_EMAIL,
                    to=[settings.DEFAULT_FROM_EMAIL], bcc=unique[i:i + size],
                ).send()
            except Exception as exc:  # noqa: BLE001
                log.error("Bulk email batch failed: %s", exc)

    if unique:
        _run(work)


__all__ = ["send_code_email", "send_simple", "notify_members", "EmailMessage"]
