import json

from django.test import override_settings

from .support import ViewTestCase


class PublicPagesTests(ViewTestCase):
    def test_public_pages_render(self):
        for url in ("/", "/about/", "/services/", "/contact/", "/treasury/", "/login/", "/register/",
                    "/forgot/", "/offline/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_pwa_files(self):
        r = self.client.get("/manifest.webmanifest")
        self.assertEqual(json.loads(r.content)["short_name"], "AEPS-ALUMNI")
        self.assertIn("javascript", self.client.get("/sw.js")["Content-Type"])

    def test_private_pages_require_login(self):
        for url in ("/feed/", "/members/", "/messages/", "/events/", "/gallery/", "/cotisations/", "/profile/"):
            with self.subTest(url=url):
                r = self.client.get(url)
                self.assertEqual(r.status_code, 302)
                self.assertIn("/login/", r["Location"])


class MemberPagesTests(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.login("1")

    def test_pages_render(self):
        for url in ("/feed/", "/members/", "/events/", "/gallery/", "/cotisations/", "/jobs/propose/", "/profile/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_directory_hides_pending_members_and_filters(self):
        body = self.client.get("/members/").content.decode()
        self.assertIn("Prenom1", body)
        self.assertNotIn("Prenom3", body)  # inscription non validée
        body = self.client.get("/members/?mentor=1").content.decode()
        self.assertIn("Prenom2", body)
        self.assertNotIn("Prenom1 Nom1", body)

    def test_feed_shows_apply_button(self):
        self.assertIn("mailto:rh@acme.fr", self.client.get("/feed/").content.decode())

    def test_feed_like_and_comment(self):
        self.client.get("/feed/")  # pose le cookie CSRF
        csrf = self.client.cookies["csrftoken"].value
        r = self.client.post("/feed/news/1/like/", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"liked": True, "count": 1})
        r = self.client.post("/feed/news/1/like/", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(r.json(), {"liked": False, "count": 0})

        r = self.client.post("/feed/news/1/comment/", json.dumps({"body": "Bravo !"}),
                              content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["comment"]["body"], "Bravo !")
        body = self.client.get("/feed/news/1/comments/").json()
        self.assertEqual(len(body["comments"]), 1)

        r = self.client.post("/feed/news/999/comment/", json.dumps({"body": "x"}),
                              content_type="application/json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(r.status_code, 404)


class MessagingTests(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.login("1")

    def post(self, payload):
        return self.client.post("/messages/api/send/", json.dumps(payload), content_type="application/json")

    def test_send_and_read(self):
        self.assertEqual(self.post({"to": "m2@x.fr", "text": "Salut"}).status_code, 200)
        r = self.client.get("/messages/api/conversation/?with=m2@x.fr").json()
        self.assertEqual([m["text"] for m in r["messages"]], ["Salut"])

    def test_rejects_unknown_or_pending_recipient_and_self(self):
        self.assertEqual(self.post({"to": "m3@x.fr", "text": "x"}).status_code, 400)  # compte non validé
        self.assertEqual(self.post({"to": "nobody@x.fr", "text": "x"}).status_code, 400)
        self.assertEqual(self.post({"to": "m1@x.fr", "text": "x"}).status_code, 400)

    def test_rejects_bad_payloads(self):
        self.assertEqual(self.post({"to": "m2@x.fr", "text": "[AUDIO]javascript:1"}).status_code, 400)
        self.assertEqual(self.post({"to": "m2@x.fr", "text": "[CALL]video:../x"}).status_code, 400)
        self.assertEqual(self.post({"to": "m2@x.fr", "text": "a" * 20000}).status_code, 400)

    def test_group_chat_limited_to_own_promo(self):
        self.assertEqual(self.post({"to": "promo:2020", "text": "Bonjour la promo"}).status_code, 200)
        self.assertEqual(self.post({"to": "promo:2021", "text": "intrus"}).status_code, 403)
        self.assertEqual(self.client.get("/messages/api/conversation/?with=promo:2021").status_code, 403)

    def test_api_requires_login(self):
        anonymous = self.client_class()
        self.assertEqual(anonymous.get("/messages/api/contacts/").status_code, 401)

    def test_send_is_rate_limited(self):
        codes = [self.post({"to": "m2@x.fr", "text": str(i)}).status_code for i in range(65)]
        self.assertIn(429, codes)


class AdminTests(ViewTestCase):
    def test_admin_login_wrong_and_right_password(self):
        self.assertIn("incorrect", self.client.post("/responsable/", {"password": "nope"}).content.decode())
        self.assertEqual(self.client.post("/responsable/", {"password": "adm"}).status_code, 302)
        for tab in ("dashboard", "members", "news", "jobs", "events", "dues"):
            with self.subTest(tab=tab):
                self.assertEqual(self.client.get(f"/responsable/?tab={tab}").status_code, 200)

    def test_admin_actions_require_admin(self):
        self.login("1")
        r = self.client.post("/responsable/members/2/delete/")
        self.assertNotEqual(r.status_code, 200)
        self.assertEqual(len(self.store.members), 3)

    def test_validate_pending_member_and_csv_export(self):
        self.client.post("/responsable/", {"password": "adm"})
        self.client.post("/responsable/members/3/status/", {"status": "active"})
        self.assertEqual(self.store.members[2]["status"], "active")
        self.store.members[0]["first_name"] = "=HYPERLINK(\"x\")"
        csv_body = self.client.get("/responsable/export/members.csv").content.decode("utf-8-sig")
        self.assertNotIn(";=HYPERLINK", csv_body)

    def test_print_list_by_promo(self):
        self.assertEqual(self.client.get("/responsable/members/print/?promo=2020").status_code, 302)  # protégé
        self.client.post("/responsable/", {"password": "adm"})
        body = self.client.get("/responsable/members/print/?promo=2021").content.decode()
        self.assertIn("promotion 2021", body)
        self.assertIn("Prenom2", body)
        self.assertNotIn("Prenom1", body)

    def test_responsable_sets_due_rate_for_everyone(self):
        self.client.post("/responsable/", {"password": "adm"})
        r = self.client.post("/responsable/dues/set-rate/", {"year": "2026", "amount": "7500"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.store.due_rates[2026], 7500)
        self.assertEqual(len(self.store.dues), 2)  # les 2 membres actifs (le 3e est en attente de validation)
        self.assertTrue(all(d["amount"] == 7500 for d in self.store.dues))

        # Un membre règle sa cotisation au montant en vigueur...
        self.store.dues[0]["status"] = "paid"
        # ...puis les responsables changent le montant : il s'applique à tous les membres non payés,
        # sans exception, mais ne modifie jamais une cotisation déjà réglée.
        r = self.client.post("/responsable/dues/set-rate/", {"year": "2026", "amount": "9000"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.store.due_rates[2026], 9000)
        self.assertEqual(self.store.dues[0]["amount"], 7500)  # déjà payée : inchangée
        self.assertEqual(self.store.dues[1]["amount"], 9000)  # pas encore payée : alignée

        r = self.client.post("/responsable/dues/set-rate/", {"year": "2026", "amount": "0"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.store.due_rates[2026], 9000)  # montant invalide : inchangé

    def test_role_based_admin_is_revoked_when_role_removed(self):
        self.store.members[0]["role"] = "admin"
        self.login("1")  # la connexion d'un admin ouvre l'espace Responsable
        self.assertEqual(self.client.get("/responsable/?tab=members").status_code, 200)
        self.store.members[0]["role"] = "member"
        self.assertIn("Accès", self.client.get("/responsable/").content.decode())


@override_settings(CINETPAY_API_KEY="", CINETPAY_SITE_ID="")
class PaymentTests(ViewTestCase):
    def test_notify_without_reference_is_harmless(self):
        r = self.client.post("/cotisations/notification/", {"cpm_trans_id": "unknown"})
        self.assertIn(r.status_code, (200, 400, 404))
