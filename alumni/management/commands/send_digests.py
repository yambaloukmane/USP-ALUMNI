"""Rappels par e-mail pour les messages non lus.

À lancer régulièrement (toutes les 15 à 30 minutes) avec une tâche planifiée :
    python manage.py send_digests
Un membre n'est prévenu qu'une fois par message, et seulement s'il ne l'a pas lu au bout de N minutes.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand
from django.urls import reverse

from alumni import data_service as ds
from alumni import emails
from alumni.views._common import external_url


class Command(BaseCommand):
    help = "Envoie un e-mail aux membres qui ont des messages non lus depuis un moment."

    def add_arguments(self, parser):
        parser.add_argument("--minutes", type=int, default=15, help="Délai avant rappel (défaut : 15)")
        parser.add_argument("--dry-run", action="store_true", help="Affiche sans envoyer")

    def handle(self, *args, **options):
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=options["minutes"])).isoformat()
        pending = ds.get_unnotified_messages(cutoff)
        by_receiver: dict[str, list[dict]] = defaultdict(list)
        for msg in pending:
            by_receiver[msg["receiver_id"]].append(msg)

        members = {m["email"]: m for m in ds.get_active_members() if m.get("email")}
        sent = 0
        for email, msgs in by_receiver.items():
            member = members.get(email)
            if not member:
                continue
            senders = {m["sender_id"] for m in msgs}
            count = len(msgs)
            body = (f"Bonjour {member.get('first_name', '')},\n\n"
                    f"Vous avez {count} message{'s' if count > 1 else ''} non lu{'s' if count > 1 else ''} "
                    f"de la part de {len(senders)} membre{'s' if len(senders) > 1 else ''} sur AEPS-ALUMNI.\n\n"
                    f"Lire mes messages : {external_url(reverse('messages'))}\n")
            self.stdout.write(f"{email} : {count} message(s)")
            if not options["dry_run"]:
                emails.send_simple(email, "Vous avez des messages non lus sur AEPS-ALUMNI", body)
                ds.mark_notified([m["id"] for m in msgs])
                sent += 1
        self.stdout.write(self.style.SUCCESS(f"{sent} e-mail(s) envoyé(s)."))
