"""Faux magasin de données en mémoire : les tests n'appellent jamais Supabase."""
from unittest import mock

from django.core.cache import cache
from django.test import Client, SimpleTestCase, override_settings

from alumni import data_service as ds


def member(i, **kw):
    base = {"id": str(i), "email": f"m{i}@x.fr", "first_name": f"Prenom{i}", "last_name": f"Nom{i}",
            "promo": "2020", "job": "Dev", "sector": "Informatique", "city": "Abidjan", "country": "CI",
            "bio": "", "phone": "", "linkedin": "", "is_mentor": False, "role": "member", "status": "active",
            "created_at": "2024-01-01T00:00:00+00:00"}
    base.update(kw)
    return base


class Store:
    def __init__(self):
        self.members = [member(1), member(2, promo="2021", is_mentor=True), member(3, status="pending")]
        self.messages = []
        self.news = [{"id": "1", "title": "T", "desc": "D", "img": "", "date": "01/01/2024"}]
        self.jobs = [{"id": "1", "title": "Dev", "company": "ACME", "location": "Abidjan", "salary": "", "type": "CDI",
                      "status": "approved", "apply_contact": "rh@acme.fr", "expires_at": None}]
        self.events, self.rsvps, self.dues, self.photos = [], [], [], []
        self.likes, self.comments = [], []

    def install(self, testcase):
        s = self

        def _toggle_like(post_type, post_id, member_id):
            key = (post_type, str(post_id), str(member_id))
            existing = next((l for l in s.likes if (l["post_type"], str(l["post_id"]), str(l["member_id"])) == key), None)
            if existing:
                s.likes.remove(existing)
                return False
            s.likes.append({"post_type": post_type, "post_id": str(post_id), "member_id": str(member_id)})
            return True

        def _add_comment(post_type, post_id, member_id, body):
            c = {"id": str(len(s.comments) + 1), "post_type": post_type, "post_id": str(post_id),
                 "member_id": str(member_id), "body": body, "created_at": "2024-01-01T00:00:00+00:00"}
            s.comments.append(c)
            return c

        def _sm(me, to, text, label):
            m = {"id": str(len(s.messages) + 1), "sender_id": me, "receiver_id": to, "text": text, "time": label,
                 "is_read": False, "created_at": f"2024-01-01T00:00:{len(s.messages):02d}+00:00"}
            s.messages.append(m)
            return m
        patches = {
            "check_connection": lambda: "OK", "schema_v3": lambda: True,
            "get_members": lambda: s.members,
            "get_active_members": lambda: [m for m in s.members if m["status"] == "active"],
            "get_member_cached": lambda i: next((m for m in s.members if m["id"] == str(i)), None),
            "get_member_by_id": lambda i: next((m for m in s.members if m["id"] == str(i)), None),
            "get_member_by_email": lambda e: next((m for m in s.members if m["email"] == e), None),
            "get_member_avatar": lambda i: "",
            "authenticate": lambda e, p: dict(next((m for m in s.members if m["email"] == e), {})) or None if p == "pw" else None,
            "get_news": lambda: s.news, "get_jobs": lambda: s.jobs, "get_public_jobs": lambda: s.jobs,
            "get_events": lambda: s.events, "get_rsvps": lambda: s.rsvps, "get_photos": lambda: s.photos,
            "get_dues": lambda year=None: s.dues, "get_member_dues": lambda i: [d for d in s.dues if d["member_id"] == i],
            "get_or_create_due": lambda m, y, a: None, "get_due_by_reference": lambda r: None,
            "get_contact_summaries": lambda me: {},
            "get_group_last": lambda room: None,
            "get_group_conversation": lambda room, after=None: [m for m in s.messages if m["receiver_id"] == room],
            "get_conversation": lambda me, o, after=None: [m for m in s.messages if {m["sender_id"], m["receiver_id"]} == {me, o}],
            "mark_as_read": lambda a, b: None, "get_unread_count": lambda e: 0, "save_message": _sm,
            "add_news": lambda *a, **k: None, "delete_member": lambda i: s.members.remove(next(m for m in s.members if m["id"] == i)),
            "admin_update_member": lambda i, f: next(m for m in s.members if m["id"] == i).update(f),
            "get_likes": lambda: s.likes, "toggle_like": _toggle_like,
            "get_comment_counts": lambda: {
                f"{c['post_type']}:{c['post_id']}": sum(1 for x in s.comments if x["post_type"] == c["post_type"] and x["post_id"] == c["post_id"])
                for c in s.comments
            },
            "get_comments": lambda pt, pid: [c for c in s.comments if c["post_type"] == pt and c["post_id"] == str(pid)],
            "get_comment": lambda cid: next((c for c in s.comments if c["id"] == str(cid)), None),
            "add_comment": _add_comment,
            "delete_comment": lambda cid: s.comments.remove(next(c for c in s.comments if c["id"] == str(cid))),
        }
        for name, fn in patches.items():
            p = mock.patch.object(ds, name, fn)
            p.start()
            testcase.addCleanup(p.stop)


@override_settings(ADMIN_PASSWORD="adm", SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
                   CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class ViewTestCase(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.store = Store()
        self.store.install(self)
        self.client = Client()

    def login(self, member_id="1"):
        m = next(m for m in self.store.members if m["id"] == member_id)
        r = self.client.post("/login/", {"email": m["email"], "password": "pw"})
        assert r.status_code == 302, "connexion de test refusée"
