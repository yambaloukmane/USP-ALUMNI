from unittest import mock

from django.http import QueryDict
from django.test import SimpleTestCase

from alumni.profile_form import form_values, parse_profile

from .support import ViewTestCase


def post(**kw):
    q = QueryDict(mutable=True)
    base = {"first_name": "Awa", "last_name": "Koné", "phone": "+225 07 00 00 00 00", "promo": "2020",
            "situation": "Étudiant", "country": "Côte d'Ivoire", "terms": "on"}
    base.update(kw)
    for k, v in base.items():
        if isinstance(v, list):
            q.setlist(k, v)
        else:
            q[k] = v
    return q


class ParseProfileTests(SimpleTestCase):
    def test_valid_registration(self):
        data, error, step = parse_profile(post(offers=["mentorat", "stages", "hack"], seeks=["stage"]), True)
        self.assertEqual((error, step), ("", 0))
        self.assertEqual(data["offers"], ["mentorat", "stages"])  # valeurs inconnues ignorées
        self.assertTrue(data["is_mentor"])
        self.assertFalse(data["show_email"])  # confidentialité par défaut

    def test_required_fields_point_to_the_right_step(self):
        self.assertEqual(parse_profile(post(promo="20"), True)[2], 2)
        self.assertEqual(parse_profile(post(situation=""), True)[2], 3)
        self.assertEqual(parse_profile(post(country=""), True)[2], 3)
        self.assertEqual(parse_profile(post(terms=""), True)[2], 4)
        self.assertEqual(parse_profile(post(phone=""), True)[2], 1)

    def test_entry_year_cannot_follow_promo(self):
        self.assertTrue(parse_profile(post(entry_year="2022"), True)[1])
        self.assertEqual(parse_profile(post(entry_year="2018"), True)[1], "")

    def test_linkedin_must_be_https(self):
        self.assertTrue(parse_profile(post(linkedin="javascript:alert(1)"), True)[1])

    def test_other_school_uses_typed_name_and_none_clears_track(self):
        data = parse_profile(post(school="Autre école (préciser)", school_other="ENSEA", school_track="Info"), True)[0]
        self.assertEqual(data["school"], "ENSEA")
        self.assertEqual(form_values(data)["school"], "Autre école (préciser)")
        data = parse_profile(post(school="Pas encore intégré", school_track="Info"), True)[0]
        self.assertEqual(data["school_track"], "")

    def test_profile_edit_does_not_require_registration_fields(self):
        self.assertEqual(parse_profile(post(terms="", phone="", situation="", country=""), False)[1], "")


class RegistrationViewTests(ViewTestCase):
    def test_form_renders_four_steps(self):
        body = self.client.get("/register/").content.decode()
        for n in (1, 2, 3, 4):
            self.assertIn(f'data-step="{n}"', body)

    def test_valid_registration_sends_code(self):
        form = {"first_name": "Awa", "last_name": "Koné", "email": "new@x.fr", "password": "motdepasse1",
                "phone": "+225 07 00 00 00 00", "promo": "2020", "situation": "Étudiant", "country": "Côte d'Ivoire",
                "terms": "on", "offers": ["mentorat"]}
        with mock.patch("alumni.emails.send_code_email") as send:
            r = self.client.post("/register/", form)
        self.assertEqual(r.status_code, 302)
        self.assertIn("verify", r["Location"])
        send.assert_called_once()

    def test_error_reopens_the_faulty_step(self):
        r = self.client.post("/register/", {"first_name": "A", "last_name": "B", "email": "n@x.fr", "password": "motdepasse1",
                                            "phone": "+225 07 00 00 00 00", "promo": "abc", "terms": "on"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["error_step"], 2)

    def test_short_password_rejected(self):
        r = self.client.post("/register/", {"first_name": "A", "last_name": "B", "email": "n@x.fr", "password": "abc"})
        self.assertIn("8 caractères", r.context["error"])


class DirectoryPrivacyTests(ViewTestCase):
    def test_contact_details_hidden_unless_allowed(self):
        self.store.members[1].update(phone="+22507112233", show_phone=False, show_email=False)
        self.login("1")
        body = self.client.get("/members/").content.decode()
        self.assertNotIn("+22507112233", body)
        self.assertNotIn("m2@x.fr", body)
        self.store.members[1].update(show_phone=True, show_email=True)
        body = self.client.get("/members/").content.decode()
        self.assertIn("+22507112233", body)
        self.assertIn("m2@x.fr", body)

    def test_referent_never_shown_to_members(self):
        self.store.members[1]["referent"] = "SECRET-REFERENT"
        self.login("1")
        self.assertNotIn("SECRET-REFERENT", self.client.get("/members/").content.decode())

    def test_profile_page_and_save(self):
        self.login("1")
        self.assertEqual(self.client.get("/profile/").status_code, 200)
