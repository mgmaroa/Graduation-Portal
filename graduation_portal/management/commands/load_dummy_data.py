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

# (course, school)
COURSES = [
    ("Diploma in Information Communication Technology", "School of Computing and Informatics"),
    ("Diploma in Business Management", "School of Business"),
    ("Diploma in Electrical and Electronic Engineering", "School of Engineering"),
    ("Diploma in Civil Engineering", "School of Engineering"),
    ("Certificate in Hospitality Management", "School of Hospitality and Tourism"),
]

# Easy numbers to remember when demoing the lookup
DEMO_NUMBERS = [11300, 9876, 11256]


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

        # Start with memorable numbers for demos, then fill with random 4-5 digit ones
        numbers = DEMO_NUMBERS[: opts["count"]]
        pool = [n for n in range(9000, 12000) if n not in numbers]
        numbers += rng.sample(pool, max(0, opts["count"] - len(numbers)))

        created = 0
        rows = []
        for i, number in enumerate(numbers):
            course, school = COURSES[i % len(COURSES)]
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"

            obj, was_created = Graduand.objects.update_or_create(
                admission_no=str(number),
                defaults={
                    "student_name": name,
                    "course": course,
                    "school": school,
                    "graduation_date": grad_date,
                    "is_dummy": True,
                },
            )
            created += was_created
            rows.append((obj.admission_no, name))

        self.stdout.write(self.style.SUCCESS(
            f"Dummy data ready: {created} created, {opts['count'] - created} already existed."
        ))
        self.stdout.write("\nTry these admission numbers in the lookup:")
        for adm, name in rows[:5]:
            self.stdout.write(f"  {adm:<8} {name}")
        self.stdout.write("  ...and anything NOT in the list (e.g. 10000) to test the regret page.")