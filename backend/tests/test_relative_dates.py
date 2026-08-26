import unittest
from datetime import date

from app.services.relative_dates import resolve_schedule


class RelativeDateTests(unittest.TestCase):
    REF = date(2026, 8, 6)

    def test_taptap_week_of_24_day_26_stays_august(self):
        self.assertEqual(
            resolve_schedule("semana del 24, el 26", self.REF),
            "2026-08-26",
        )

    def test_around_the_20th_of_september(self):
        self.assertEqual(
            resolve_schedule("20 y pico de septiembre", self.REF),
            "2026-09-20",
        )

    def test_in_a_month(self):
        self.assertEqual(resolve_schedule("en un mes", self.REF), "2026-09-06")
        self.assertEqual(resolve_schedule("in a month", self.REF), "2026-09-06")

    def test_weekday_does_not_override_day_of_month(self):
        # 26 Mar 2026 is a Thursday — the old model guess. Day-of-month wins.
        self.assertEqual(
            resolve_schedule("semana del 24, el 26, jueves", self.REF),
            "2026-08-26",
        )
        self.assertNotEqual(
            resolve_schedule("el 26 jueves", self.REF),
            "2026-03-26",
        )

    def test_week_of_24_on_call_day_26_stays_this_month(self):
        self.assertEqual(
            resolve_schedule("semana del 24", date(2026, 8, 26)),
            "2026-08-24",
        )


if __name__ == "__main__":
    unittest.main()
