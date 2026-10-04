from datetime import date, timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Graduand, LookupAttempt
from .utils import normalize_admission_no


def make_graduand(adm="11300", **kw):
    data = dict(
        admission_no=adm, student_name="Amani Kariuki",
        course="Diploma in Information Communication Technology",
        school="School of Computing and Informatics",
        graduation_date=date(2026, 11, 11),
    )
    data.update(kw)
    return Graduand.objects.create(**data)


class NormalizeTests(TestCase):
    def test_strips_whitespace(self):
        self.assertEqual(normalize_admission_no("  11 300 "), "11300")

    def test_excel_float_becomes_plain_number(self):
        self.assertEqual(normalize_admission_no(11300.0), "11300")
        self.assertEqual(normalize_admission_no("9876.0"), "9876")

    def test_none_and_empty(self):
        self.assertEqual(normalize_admission_no(None), "")
        self.assertEqual(normalize_admission_no("   "), "")


class GraduandModelTests(TestCase):
    def test_save_normalizes_admission_no(self):
        self.assertEqual(make_graduand(" 11300.0 ").admission_no, "11300")


class DummyDataCommandTests(TestCase):
    def test_creates_requested_count_flagged_as_dummy(self):
        call_command("load_dummy_data", "--count", "12", stdout=StringIO())
        self.assertEqual(Graduand.objects.count(), 12)
        self.assertEqual(Graduand.objects.filter(is_dummy=True).count(), 12)

    def test_includes_demo_numbers_and_all_are_numeric(self):
        call_command("load_dummy_data", "--count", "30", stdout=StringIO())
        for n in ("11300", "9876", "11256"):
            self.assertTrue(Graduand.objects.filter(admission_no=n).exists())
        self.assertTrue(all(a.isdigit() and 4 <= len(a) <= 5
                            for a in Graduand.objects.values_list("admission_no", flat=True)))

    def test_is_idempotent(self):
        call_command("load_dummy_data", "--count", "10", stdout=StringIO())
        call_command("load_dummy_data", "--count", "10", stdout=StringIO())
        self.assertEqual(Graduand.objects.count(), 10)

    def test_clear_removes_only_dummy_records(self):
        real = make_graduand("12345", is_dummy=False)
        call_command("load_dummy_data", "--count", "5", stdout=StringIO())
        call_command("load_dummy_data", "--only-clear", stdout=StringIO())
        self.assertEqual(list(Graduand.objects.values_list("pk", flat=True)), [real.pk])


class LookupViewTests(TestCase):
    url = "/"

    def setUp(self):
        # django-simple-captcha reads its test flag at import time, so patch it directly.
        # In test mode the answer "PASSED" is accepted as a correct CAPTCHA.
        patcher = mock.patch("captcha.conf.settings.CAPTCHA_TEST_MODE", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, adm, captcha="PASSED"):
        return self.client.post(self.url, {
            "admission_no": adm, "captcha_0": "dummy", "captcha_1": captcha,
        })

    def test_get_shows_form_with_privacy_headers(self):
        r = self.client.get(self.url)
        self.assertContains(r, "Confirm your graduation status")
        self.assertIn("noindex", r["X-Robots-Tag"])
        self.assertIn("no-store", r["Cache-Control"])

    def test_found_shows_all_five_details(self):
        make_graduand("11300")
        r = self.post("11300")
        self.assertContains(r, "You are on the graduation list")
        for text in ("Amani Kariuki", "11300", "Diploma in Information Communication Technology",
                     "School of Computing and Informatics", "Wednesday, 11 November 2026"):
            self.assertContains(r, text)
        self.assertIn("no-store", r["Cache-Control"])

    def test_input_is_normalized_before_matching(self):
        make_graduand("11300")
        self.assertContains(self.post(" 11300 "), "You are on the graduation list")
        self.assertContains(self.post("11300.0"), "You are on the graduation list")

    def test_not_found_shows_required_wording(self):
        r = self.post("10000")
        self.assertContains(r, "Not found on the current list")
        self.assertNotContains(r, "Amani")

    def test_regret_does_not_echo_the_number(self):
        self.assertNotContains(self.post("10001"), "10001")

    def test_invalid_format_rejected_and_not_logged(self):
        for bad in ("abc", "12", "1234567", "DICT/001/2023"):
            r = self.post(bad)
            self.assertContains(r, "digits only")
        self.assertEqual(LookupAttempt.objects.count(), 0)

    def test_wrong_captcha_rejected_even_for_valid_number(self):
        make_graduand("11300")
        r = self.post("11300", captcha="wrong")
        self.assertNotContains(r, "Amani Kariuki")
        self.assertEqual(LookupAttempt.objects.count(), 0)

    def test_attempts_are_logged(self):
        make_graduand("11300")
        self.post("11300")
        self.post("10000")
        self.assertEqual(LookupAttempt.objects.filter(found=True).count(), 1)
        self.assertEqual(LookupAttempt.objects.filter(found=False).count(), 1)

    @override_settings(LOOKUP_MAX_NOT_FOUND=3)
    def test_too_many_not_found_blocks_with_429(self):
        for _ in range(3):
            LookupAttempt.objects.create(ip_address="127.0.0.1", searched_value="1", found=False)
        r = self.post("11300")
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, "Too many attempts", status_code=429)
        self.assertIn("Retry-After", r)

    @override_settings(LOOKUP_MAX_NOT_FOUND=3)
    def test_old_attempts_do_not_block(self):
        old = timezone.now() - timedelta(hours=1)
        for _ in range(3):
            a = LookupAttempt.objects.create(ip_address="127.0.0.1", searched_value="1", found=False)
            LookupAttempt.objects.filter(pk=a.pk).update(created_at=old)
        self.assertEqual(self.post("10000").status_code, 200)

    @override_settings(LOOKUP_MAX_NOT_FOUND=3)
    def test_other_ips_are_not_blocked(self):
        for _ in range(3):
            LookupAttempt.objects.create(ip_address="10.9.9.9", searched_value="1", found=False)
        self.assertEqual(self.post("10000").status_code, 200)

    def test_robots_txt_disallows_everything(self):
        self.assertContains(self.client.get("/robots.txt"), "Disallow: /")

    def test_put_not_allowed(self):
        self.assertEqual(self.client.put(self.url).status_code, 405)