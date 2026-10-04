from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from .models import Graduand
from .utils import normalize_admission_no


class NormalizeTests(TestCase):
    def test_trims_uppercases_and_fixes_slash_spacing(self):
        self.assertEqual(normalize_admission_no("  abc/123/2020 "), "ABC/123/2020")
        self.assertEqual(normalize_admission_no("abc / 123 / 2020"), "ABC/123/2020")

    def test_none_and_empty(self):
        self.assertEqual(normalize_admission_no(None), "")
        self.assertEqual(normalize_admission_no("   "), "")


class GraduandModelTests(TestCase):
    def test_save_normalizes_admission_no(self):
        g = Graduand.objects.create(
            admission_no=" dict/001/2023 ", student_name="Test Student",
            course="Diploma in ICT", school="Computing", graduation_date=date(2026, 11, 11),
        )
        self.assertEqual(g.admission_no, "DICT/001/2023")

    def test_lookup_is_case_insensitive_after_normalizing(self):
        Graduand.objects.create(
            admission_no="DICT/001/2023", student_name="A", course="C",
            school="S", graduation_date=date(2026, 11, 11),
        )
        found = Graduand.objects.filter(admission_no=normalize_admission_no("dict / 001 / 2023"))
        self.assertTrue(found.exists())


class DummyDataCommandTests(TestCase):
    def test_creates_requested_count_flagged_as_dummy(self):
        call_command("load_dummy_data", "--count", "12", stdout=StringIO())
        self.assertEqual(Graduand.objects.count(), 12)
        self.assertEqual(Graduand.objects.filter(is_dummy=True).count(), 12)

    def test_is_idempotent(self):
        call_command("load_dummy_data", "--count", "10", stdout=StringIO())
        call_command("load_dummy_data", "--count", "10", stdout=StringIO())
        self.assertEqual(Graduand.objects.count(), 10)

    def test_clear_removes_only_dummy_records(self):
        real = Graduand.objects.create(
            admission_no="REAL/001/2022", student_name="Real Student", course="C",
            school="S", graduation_date=date(2026, 11, 11), is_dummy=False,
        )
        call_command("load_dummy_data", "--count", "5", stdout=StringIO())
        call_command("load_dummy_data", "--only-clear", stdout=StringIO())
        self.assertEqual(Graduand.objects.count(), 1)
        self.assertEqual(Graduand.objects.get().pk, real.pk)