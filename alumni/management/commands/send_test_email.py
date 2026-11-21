"""Teste l'envoi d'e-mails : python manage.py send_test_email adresse@exemple.com"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envoie un e-mail de test pour vérifier la configuration SMTP."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Adresse qui reçoit le test")

    def handle(self, *args, **options):
        self.stdout.write(f"Serveur : {settings.EMAIL_BACKEND.rsplit('.', 2)[-2]} "
                          f"({settings.EMAIL_HOST}:{settings.EMAIL_PORT}) — expéditeur : {settings.DEFAULT_FROM_EMAIL}")
        if settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
            self.stdout.write(self.style.WARNING(
                "Mode console : aucun vrai e-mail n'est envoyé. Renseignez EMAIL_HOST_USER et "
                "EMAIL_HOST_PASSWORD dans .env."))
        try:
            send_mail("Test AEPS-ALUMNI", "Si vous lisez ceci, l'envoi d'e-mails fonctionne.",
                      settings.DEFAULT_FROM_EMAIL, [options["to"]])
        except Exception as exc:  # noqa: BLE001
            raise CommandError(f"Échec de l'envoi : {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"E-mail envoyé à {options['to']}."))
