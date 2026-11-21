from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from alumni import ratelimit
from alumni.views._common import external_url, valid_email
from alumni.views.admin_area import _safe_cell
from alumni.views.messaging import CALL_RE, _valid_text
from alumni.views.network import _apply_link, _matches


class RateLimitTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_blocks_after_limit(self):
        results = [ratelimit.hit("t", "ip", 3, 60) for _ in range(5)]
        self.assertEqual(results, [True, True, True, False, False])

    def test_scopes_are_independent(self):
        for _ in range(3):
            ratelimit.hit("a", "ip", 3, 60)
        self.assertTrue(ratelimit.hit("b", "ip", 3, 60))


class HelperTests(SimpleTestCase):
    def test_csv_formula_injection_is_neutralised(self):
        for dangerous in ("=1+1", "+cmd", "-2", "@SUM(A1)"):
            self.assertTrue(_safe_cell(dangerous).startswith("'"))
        self.assertEqual(_safe_cell("Marie"), "Marie")
        self.assertEqual(_safe_cell(None), "")

    def test_call_message_format(self):
        self.assertTrue(CALL_RE.match("[CALL]video:aeps-0123456789abcdef"))
        self.assertFalse(CALL_RE.match("[CALL]video:<script>"))
        self.assertFalse(CALL_RE.match("[CALL]audio:short"))

    def test_voice_messages_must_be_https(self):
        self.assertTrue(_valid_text("[AUDIO]https://x.supabase.co/storage/v1/a.webm"))
        self.assertFalse(_valid_text("[AUDIO]javascript:alert(1)"))
        self.assertFalse(_valid_text("[AUDIO]data:audio/webm;base64,AAAA"))

    def test_email_validation(self):
        self.assertTrue(valid_email("a@b.fr"))
        self.assertFalse(valid_email("a@b"))
        self.assertFalse(valid_email("a b@c.fr"))

    @override_settings(SITE_URL="https://alumni.example.org/")
    def test_external_url(self):
        self.assertEqual(external_url("/feed/"), "https://alumni.example.org/feed/")

    def test_apply_link(self):
        self.assertEqual(_apply_link({"apply_contact": "rh@x.fr"}), ("mailto:rh@x.fr", False))
        self.assertEqual(_apply_link({"apply_contact": "https://x.fr/job"}), ("https://x.fr/job", True))
        self.assertEqual(_apply_link({"apply_contact": "javascript:alert(1)"})[0], "/contact/")

    def test_member_filters(self):
        m = {"first_name": "Ann", "last_name": "Lee", "promo": "2020", "sector": "IT", "country": "CI",
             "is_mentor": True, "city": "", "job": ""}
        base = {"q": "", "promo": "", "sector": "", "country": "", "mentor": False, "school": "", "situation": ""}
        self.assertTrue(_matches(m, {**base, "q": "lee"}))
        self.assertFalse(_matches(m, {**base, "promo": "2021"}))
        self.assertTrue(_matches(m, {**base, "mentor": True}))
