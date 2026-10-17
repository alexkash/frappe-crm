"""Inclusive service periods anchored to the original contract start date."""

import calendar
from datetime import date, timedelta

MONTHS = {"Monthly": 1, "Quarterly": 3, "Half-yearly": 6, "Yearly": 12}


def period_for_index(start: date, end: date, cadence: str, index: int) -> tuple[date, date] | None:
	if type(start) is not date or type(end) is not date or end < start:
		raise ValueError("Invalid contract dates")
	if type(index) is not int or index < 0 or cadence not in {*MONTHS, "One-time"}:
		raise ValueError("Invalid period")
	if cadence == "One-time":
		return (start, end) if index == 0 else None

	def boundary(n):
		month = start.year * 12 + start.month - 1 + MONTHS[cadence] * n
		year, month = divmod(month, 12)
		return date(year, month + 1, min(start.day, calendar.monthrange(year, month + 1)[1]))

	first = boundary(index)
	if first > end:
		return None
	return first, min(end, boundary(index + 1) - timedelta(days=1))
