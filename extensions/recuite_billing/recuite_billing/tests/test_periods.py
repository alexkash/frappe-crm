import unittest
from datetime import date

from recuite_billing.periods import is_partial_period, period_for_index


class TestPeriods(unittest.TestCase):
	def test_detects_clipped_and_off_schedule_periods_for_explicit_confirmation(self):
		cases = [
			("2026-01-01", "2026-12-31", "Yearly", "2026-01-01", "2026-12-31", False),
			("2026-01-01", "2026-12-15", "Yearly", "2026-01-01", "2026-12-15", True),
			("2026-01-01", "2026-12-31", "Quarterly", "2026-04-01", "2026-06-30", False),
			("2026-01-01", "2026-12-31", "Monthly", "2026-01-10", "2026-01-31", True),
			("2028-01-31", "2028-12-31", "Monthly", "2028-02-29", "2028-03-30", False),
			("2026-01-01", "2026-12-15", "One-time", "2026-01-01", "2026-12-15", False),
		]
		for start, end, cadence, first, last, expected in cases:
			with self.subTest(first=first, cadence=cadence):
				self.assertEqual(
					is_partial_period(
						date.fromisoformat(start),
						date.fromisoformat(end),
						cadence,
						date.fromisoformat(first),
						date.fromisoformat(last),
					),
					expected,
				)

	def test_anchors_months_to_contract_start(self):
		for year, expected in [
			(2028, [("2028-01-31", "2028-02-28"), ("2028-02-29", "2028-03-30")]),
			(2027, [("2027-01-31", "2027-02-27"), ("2027-02-28", "2027-03-30")]),
		]:
			for index, want in enumerate(expected):
				period = period_for_index(date(year, 1, 31), date(year, 12, 31), "Monthly", index)
				self.assertEqual(tuple(x.isoformat() for x in period), want)

	def test_all_cadences_and_clipped_final_period(self):
		start, end = date(2026, 1, 1), date(2026, 12, 15)
		for cadence, index, want in [
			("Quarterly", 1, (date(2026, 4, 1), date(2026, 6, 30))),
			("Half-yearly", 1, (date(2026, 7, 1), end)),
			("Yearly", 0, (start, end)),
			("One-time", 0, (start, end)),
		]:
			self.assertEqual(period_for_index(start, end, cadence, index), want)
		self.assertIsNone(period_for_index(start, end, "Monthly", 12))
		self.assertIsNone(period_for_index(start, end, "One-time", 1))

	def test_rejects_bad_calendar_inputs(self):
		for cadence, index in [("Unknown", 0), ("Monthly", -1), ("Monthly", True)]:
			with self.assertRaises(ValueError):
				period_for_index(date(2026, 1, 1), date(2026, 12, 31), cadence, index)
