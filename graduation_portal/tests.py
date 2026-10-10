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


# ===========================================================================
# Step 5: list upload, protection of hand edits, admin editing, login lockout
# ===========================================================================
import io

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from .importer import UploadError, apply_import, build_plan, parse_upload
from .models import UploadLog

HEADER = "admission_no,student_name,course,school,graduation_date\n"


def csv_file(body, name="list.csv", header=HEADER):
    return SimpleUploadedFile(name, (header + body).encode("utf-8"), content_type="text/csv")


def xlsx_file(rows, name="list.xlsx"):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile(name, buf.getvalue())


def run_import(upload, **opts):
    parsed = parse_upload(upload)
    return apply_import(parsed.rows, parsed.rejected, parsed.total,
                        filename=upload.name, user=None, **opts)


class ParseTests(TestCase):
    def test_valid_csv(self):
        r = parse_upload(csv_file("11300,Jane Doe,Dip ICT,Computing,2026-11-11\n"))
        self.assertEqual(len(r.rows), 1)
        self.assertEqual(r.rows[0]["admission_no"], "11300")
        self.assertEqual(r.rejected, [])

    def test_alternative_headings_are_understood(self):
        f = csv_file("11300,Jane Doe,Dip ICT,Computing\n",
                     header="Adm No,Full Name,Course,Department\n")
        r = parse_upload(f)
        self.assertEqual(len(r.rows), 1)
        self.assertEqual(r.rows[0]["graduation_date"], "2026-11-11")  # default date

    def test_missing_column_gives_clear_error(self):
        with self.assertRaisesMessage(UploadError, "school or department"):
            parse_upload(csv_file("1,2,3\n", header="admission_no,student_name,course\n"))

    def test_excel_numbers_and_dates(self):
        f = xlsx_file([
            ["Admission Number", "Student Name", "Course", "School", "Graduation Date"],
            [11300.0, "  Jane   Doe ", "Dip ICT", "Computing", date(2026, 11, 11)],
            [9876, "John Roe", "Dip BM", "Business", "11/11/2026"],
        ])
        r = parse_upload(f)
        self.assertEqual([x["admission_no"] for x in r.rows], ["11300", "9876"])
        self.assertEqual(r.rows[0]["student_name"], "Jane Doe")
        self.assertEqual(r.rows[1]["graduation_date"], "2026-11-11")

    def test_bad_rows_rejected_with_reasons_and_row_numbers(self):
        r = parse_upload(csv_file(
            "11300,Jane,C,S,2026-11-11\n"
            "abc,Bad Number,C,S,2026-11-11\n"
            "11301,,C,S,2026-11-11\n"
            "11302,No School,C,,2026-11-11\n"
            "11303,Bad Date,C,S,not-a-date\n"
            "11300,Duplicate,C,S,2026-11-11\n"
            ",,,,\n"
        ))
        self.assertEqual(len(r.rows), 1)
        self.assertEqual([n for n, _ in r.rejected], [3, 4, 5, 6, 7])
        self.assertEqual(r.total, 6)  # the empty line is not counted
        reasons = " | ".join(why for _, why in r.rejected)
        for text in ("Invalid admission number", "name is blank", "School", "date", "Duplicate"):
            self.assertIn(text, reasons)

    def test_wrong_file_type_and_empty_file(self):
        with self.assertRaises(UploadError):
            parse_upload(SimpleUploadedFile("list.pdf", b"%PDF"))
        with self.assertRaises(UploadError):
            parse_upload(SimpleUploadedFile("list.csv", b"\n\n"))


class ImportBehaviourTests(TestCase):
    def test_adds_new_and_updates_existing(self):
        make_graduand("11300", student_name="Old Name")
        log = run_import(csv_file(
            "11300,New Name,Dip ICT,Computing,2026-11-11\n"
            "9876,Another Student,Dip BM,Business,2026-11-11\n"))
        self.assertEqual((log.records_added, log.records_updated), (1, 1))
        self.assertEqual(Graduand.objects.get(admission_no="11300").student_name, "New Name")
        self.assertEqual(Graduand.objects.count(), 2)

    def test_second_batch_adds_late_cleared_students_without_removing_anyone(self):
        run_import(csv_file("11300,Jane,C,S,2026-11-11\n11301,Joe,C,S,2026-11-11\n"))
        run_import(csv_file("11302,Late Cleared,C,S,2026-11-11\n"))
        self.assertEqual(sorted(Graduand.objects.values_list("admission_no", flat=True)),
                         ["11300", "11301", "11302"])

    def test_reuploading_same_list_changes_nothing(self):
        body = "11300,Jane,C,S,2026-11-11\n"
        run_import(csv_file(body))
        log = run_import(csv_file(body))
        self.assertEqual((log.records_added, log.records_updated), (0, 0))
        self.assertIn("unchanged", log.notes)

    def test_real_upload_removes_dummy_records_including_number_clashes(self):
        call_command("load_dummy_data", "--count", "10", stdout=StringIO())
        self.assertTrue(Graduand.objects.filter(admission_no="11300", is_dummy=True).exists())
        log = run_import(csv_file("11300,Real Student,Real Course,Real School,2026-11-11\n"))
        self.assertEqual(log.dummy_removed, 10)
        only = Graduand.objects.get()
        self.assertEqual((only.admission_no, only.student_name, only.is_dummy),
                         ("11300", "Real Student", False))

    def test_dummy_not_removed_when_file_has_no_valid_rows(self):
        call_command("load_dummy_data", "--count", "5", stdout=StringIO())
        run_import(csv_file("bad,row,here,x,2026-11-11\n"))
        self.assertEqual(Graduand.objects.filter(is_dummy=True).count(), 5)

    def test_can_keep_dummy_records_if_asked(self):
        call_command("load_dummy_data", "--count", "5", stdout=StringIO())
        log = run_import(csv_file("12999,Real,C,S,2026-11-11\n"), remove_dummy=False)
        self.assertEqual(log.dummy_removed, 0)
        self.assertEqual(Graduand.objects.count(), 6)

    def test_hand_edited_records_are_protected(self):
        make_graduand("11300", student_name="Corrected Name", manually_edited=True)
        log = run_import(csv_file("11300,Registrar Spelling,C,S,2026-11-11\n"))
        self.assertEqual((log.records_updated, log.records_skipped), (0, 1))
        self.assertEqual(Graduand.objects.get().student_name, "Corrected Name")
        self.assertIn("11300", log.notes)

    def test_overwrite_option_replaces_hand_edits_and_clears_flag(self):
        make_graduand("11300", student_name="Corrected Name", manually_edited=True)
        run_import(csv_file("11300,Registrar Spelling,C,S,2026-11-11\n"), overwrite_manual=True)
        g = Graduand.objects.get()
        self.assertEqual(g.student_name, "Registrar Spelling")
        self.assertFalse(g.manually_edited)

    def test_plan_reports_before_anything_is_saved(self):
        make_graduand("11300", student_name="Old")
        make_graduand("11301", manually_edited=True, student_name="Mine")
        parsed = parse_upload(csv_file(
            "11300,New,C,S,2026-11-11\n11301,Theirs,C,S,2026-11-11\n11302,Fresh,C,S,2026-11-11\n"))
        plan = build_plan(parsed.rows)
        self.assertEqual((len(plan.new), len(plan.update), len(plan.skipped_manual)), (1, 1, 1))
        labels = [c[0] for c in plan.update[0]["changes"]]
        self.assertIn("Name", labels)
        self.assertEqual(Graduand.objects.count(), 2)   # nothing saved yet

    def test_log_records_counts_and_rejections(self):
        log = run_import(csv_file("11300,Jane,C,S,2026-11-11\nbad,X,C,S,2026-11-11\n"))
        self.assertEqual((log.records_total, log.records_added, log.records_rejected), (2, 1, 1))
        self.assertIn("Row 3", log.notes)
        self.assertEqual(UploadLog.objects.count(), 1)


class AdminTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.chief = User.objects.create_superuser("ictchief", "chief@example.com", "Str0ng-Pass-123!")
        self.client.force_login(self.chief)
        self.list_url = reverse("admin:graduation_portal_graduand_changelist")

    def upload(self, body, **opts):
        data = {"file": csv_file(body)}
        data.update({k: "on" for k, v in opts.items() if v})
        return self.client.post(reverse("admin:graduation_portal_graduand_upload"), data)

    def test_changelist_shows_upload_button(self):
        self.assertContains(self.client.get(self.list_url), "Upload graduation list")

    def test_upload_page_and_template_download(self):
        self.assertContains(self.client.get(reverse("admin:graduation_portal_graduand_upload")), "Check the file")
        r = self.client.get(reverse("admin:graduation_portal_graduand_template"))
        self.assertEqual(r["Content-Type"], "text/csv")
        self.assertIn(b"admission_no,student_name", r.content)

    def test_preview_saves_nothing_then_confirm_applies(self):
        call_command("load_dummy_data", "--count", "5", stdout=StringIO())
        r = self.upload("11300,Jane Doe,Dip ICT,Computing,2026-11-11\n", remove_dummy=True)
        self.assertContains(r, "nothing has been saved yet")
        self.assertContains(r, "Apply upload")
        self.assertEqual(Graduand.objects.filter(is_dummy=True).count(), 5)
        self.assertFalse(Graduand.objects.filter(is_dummy=False).exists())

        r = self.client.post(reverse("admin:graduation_portal_graduand_upload_confirm"), follow=True)
        self.assertContains(r, "Upload applied: 1 added")
        self.assertEqual(list(Graduand.objects.values_list("admission_no", "is_dummy")), [("11300", False)])
        self.assertEqual(UploadLog.objects.get().uploaded_by, self.chief)

    def test_confirm_cannot_be_applied_twice(self):
        self.upload("11300,Jane,C,S,2026-11-11\n")
        url = reverse("admin:graduation_portal_graduand_upload_confirm")
        self.client.post(url)
        r = self.client.post(url, follow=True)
        self.assertContains(r, "expired or was already applied")
        self.assertEqual(UploadLog.objects.count(), 1)

    def test_preview_shows_rejected_rows_and_protected_records(self):
        make_graduand("11301", student_name="Mine", manually_edited=True)
        r = self.upload("11301,Theirs,C,S,2026-11-11\nbad,X,C,S,2026-11-11\n")
        self.assertContains(r, "Left alone because you edited them by hand")
        self.assertContains(r, "Invalid admission number")

    def test_bad_file_shows_friendly_error(self):
        r = self.client.post(reverse("admin:graduation_portal_graduand_upload"),
                             {"file": SimpleUploadedFile("x.pdf", b"%PDF")})
        self.assertContains(r, "Upload a .csv or .xlsx file")

    def test_editing_a_record_flags_it_as_hand_edited(self):
        g = make_graduand("11300", student_name="Wrong Spelng")
        url = reverse("admin:graduation_portal_graduand_change", args=[g.pk])
        r = self.client.post(url, {
            "admission_no": "11300", "student_name": "  Correct   Spelling ",
            "course": g.course, "school": "School of Engineering",
            "graduation_date": "2026-11-11",
        })
        self.assertEqual(r.status_code, 302)
        g.refresh_from_db()
        self.assertEqual((g.student_name, g.school), ("Correct Spelling", "School of Engineering"))
        self.assertTrue(g.manually_edited)

    def test_opening_and_saving_without_changes_does_not_flag(self):
        g = make_graduand("11300")
        url = reverse("admin:graduation_portal_graduand_change", args=[g.pk])
        self.client.post(url, {
            "admission_no": "11300", "student_name": g.student_name, "course": g.course,
            "school": g.school, "graduation_date": "2026-11-11",
        })
        g.refresh_from_db()
        self.assertFalse(g.manually_edited)

    def test_adding_a_student_by_hand(self):
        self.assertContains(self.client.get(reverse("admin:graduation_portal_graduand_add")), "2026-11-11")
        r = self.client.post(reverse("admin:graduation_portal_graduand_add"), {
            "admission_no": " 12000 ", "student_name": "Late Cleared", "course": "Dip BM",
            "school": "Business", "graduation_date": "2026-11-11",
        })
        self.assertEqual(r.status_code, 302)
        g = Graduand.objects.get(admission_no="12000")
        self.assertTrue(g.manually_edited)
        self.assertFalse(g.is_dummy)

    def test_admin_form_rejects_bad_admission_number(self):
        r = self.client.post(reverse("admin:graduation_portal_graduand_add"), {
            "admission_no": "ABC", "student_name": "X", "course": "C", "school": "S",
            "graduation_date": "2026-11-11",
        })
        self.assertContains(r, "Use digits only")
        self.assertFalse(Graduand.objects.exists())

    def test_edited_record_is_what_students_see(self):
        g = make_graduand("11300", student_name="Wrong")
        self.client.post(reverse("admin:graduation_portal_graduand_change", args=[g.pk]), {
            "admission_no": "11300", "student_name": "Right Name", "course": g.course,
            "school": g.school, "graduation_date": "2026-11-11",
        })
        with mock.patch("captcha.conf.settings.CAPTCHA_TEST_MODE", True):
            self.client.logout()
            r = self.client.post("/", {"admission_no": "11300", "captcha_0": "x", "captcha_1": "PASSED"})
        self.assertContains(r, "Right Name")

    def test_staff_without_permissions_cannot_upload(self):
        User = get_user_model()
        clerk = User.objects.create_user("clerk", password="x", is_staff=True)
        self.client.force_login(clerk)
        self.assertEqual(self.client.get(reverse("admin:graduation_portal_graduand_upload")).status_code, 403)

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        r = self.client.get(reverse("admin:graduation_portal_graduand_upload"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r["Location"])

    def test_audit_logs_are_read_only(self):
        self.assertEqual(self.client.get(reverse("admin:graduation_portal_uploadlog_add")).status_code, 403)


class LoginLockoutTests(TestCase):
    def test_repeated_failed_logins_lock_the_account_out(self):
        User = get_user_model()
        User.objects.create_superuser("ictchief", "c@example.com", "Str0ng-Pass-123!")
        url = reverse("admin:login")
        statuses = [
            self.client.post(url, {"username": "ictchief", "password": "wrong", "next": "/"}).status_code
            for _ in range(8)
        ]
        self.assertIn(429, statuses)
        # even the right password is refused during the lockout
        r = self.client.post(url, {"username": "ictchief", "password": "Str0ng-Pass-123!", "next": "/"})
        self.assertEqual(r.status_code, 429)
        self.assertContains(r, "Sign-in locked", status_code=429)