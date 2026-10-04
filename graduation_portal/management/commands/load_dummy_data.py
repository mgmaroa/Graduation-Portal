import random
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand

from graduation_portal.models import Graduand

FIRST_NAMES = [
    "Amani", "Wanjiru", "Kamau", "Achieng", "Otieno", "Njeri", "Mwangi", "Akinyi",
    "Kiprop", "Chebet", "Mutua", "Naliaka", "Barasa", "Wairimu", "Omondi", "Jepkoech",
    "Karanja", "Atieno", "Kiplagat", "Muthoni", "Odhiambo", "Nyambura", "Maina", "Adhiambo",
]
LAST_NAMES = [
    "Kariuki", "Ochieng", "Kimani", "Wekesa", "Njoroge", "Cheruiyot", "Mwende", "Onyango",
    "Githinji", "Rotich", "Mbugua", "Wafula", "Kilonzo", "Nduta", "Langat", "Owino",
]

# (code, course, school)
COURSES = [
    ("DICT", "Diploma in Information Communication Technology", "School of Computing and Informatics"),
    ("DBM", "Diploma in Business Management", "School of Business"),
    ("DEE", "Diploma in Electrical and Electronic Engineering", "School of Engineering"),
    ("DCE", "Diploma in Civil Engineering", "School of Engineering"),
    ("CHM", "Certificate in Hospitality Management", "School of Hospitality and Tourism"),
]


class Command(BaseCommand):
    help = "Load fictional graduands (flagged is_dummy) so the app can be demoed before the real list arrives."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=30, help="Number of records (default 30)")
        parser.add_argument("--clear", action="store_true",
                            help="Delete existing DUMMY records first (real records are never touched)")
        parser.add_argument("--only-clear", action="store_true",
                            help="Delete dummy records and stop")

    def handle(self, *args, **opts):
        if opts["clear"] or opts["only_clear"]:
            deleted, _ = Graduand.objects.filter(is_dummy=True).delete()
            self.stdout.write(self.style.WARNING(f"Removed {deleted} dummy record(s)."))
            if opts["only_clear"]:
                return

        rng = random.Random(42)  # fixed seed: same demo list every time
        grad_date = date.fromisoformat(settings.GRADUATION_DATE)
        counters = {code: 0 for code, _, _ in COURSES}
        created = 0
        rows = []

        for i in range(opts["count"]):
            code, course, school = COURSES[i % len(COURSES)]
            counters[code] += 1
            admission_no = f"{code}/{counters[code]:03d}/{rng.choice([2023, 2024])}"
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"

            obj, was_created = Graduand.objects.update_or_create(
                admission_no=admission_no,
                defaults={
                    "student_name": name,
                    "course": course,
                    "school": school,
                    "graduation_date": grad_date,
                    "is_dummy": True,
                },
            )
            created += was_created
            rows.append((obj.admission_no, name, code))

        self.stdout.write(self.style.SUCCESS(
            f"Dummy data ready: {created} created, {opts['count'] - created} already existed."
        ))
        self.stdout.write("\nTry these admission numbers in the lookup:")
        for adm, name, _ in rows[:5]:
            self.stdout.write(f"  {adm:<16} {name}")
        self.stdout.write("  ...and anything NOT in the list (e.g. XYZ/999/2020) to test the regret page.")
