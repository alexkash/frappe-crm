"""Inclusive service periods anchored to the original contract start date."""

import calendar
from datetime import date, timedelta

MONTHS = {"Monthly": 1, "Quarterly": 3, "Half-yearly": 6, "Yearly": 12}


def _boundary(start, months, index):
	month = start.year * 12 + start.month - 1 + months * index
	year, month = divmod(month, 12)
	return date(year, month + 1, min(start.day, calendar.monthrange(year, month + 1)[1]))


def period_for_index(start: date, end: date, cadence: str, index: int) -> tuple[date, date] | None:
	if type(start) is not date or type(end) is not date or end < start:
		raise ValueError("Invalid contract dates")
	if type(index) is not int or index < 0 or cadence not in {*MONTHS, "One-time"}:
		raise ValueError("Invalid period")
	if cadence == "One-time":
		return (start, end) if index == 0 else None

	first = _boundary(start, MONTHS[cadence], index)
	if first > end:
		return None
	return first, min(end, _boundary(start, MONTHS[cadence], index + 1) - timedelta(days=1))


def is_partial_period(start: date, end: date, cadence: str, first: date, last: date) -> bool:
	if type(first) is not date or type(last) is not date or not start <= first <= last <= end:
		raise ValueError("Period is outside the contract")
	if cadence == "One-time":
		return (first, last) != (start, end)
	if cadence not in MONTHS:
		raise ValueError("Invalid cadence")
	months = MONTHS[cadence]
	index = ((first.year - start.year) * 12 + first.month - start.month) // months
	if _boundary(start, months, index) > first:
		index -= 1
	return first != _boundary(start, months, index) or last != _boundary(
		start, months, index + 1
	) - timedelta(days=1)


def periods_in_range(anchor: date, first: date, last: date, cadence: str) -> list[tuple[date, date]]:
	if not anchor <= first <= last:
		raise ValueError("Invalid service period")
	result = []
	for index in range(1200):
		period = period_for_index(anchor, last, cadence, index)
		if period is None:
			return result
		if period[1] >= first:
			result.append((max(first, period[0]), period[1]))
	raise ValueError("Service period exceeds supported range")
