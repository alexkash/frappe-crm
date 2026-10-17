from datetime import date
from decimal import ROUND_HALF_UP, Decimal

MONTHS = (
	"січня",
	"лютого",
	"березня",
	"квітня",
	"травня",
	"червня",
	"липня",
	"серпня",
	"вересня",
	"жовтня",
	"листопада",
	"грудня",
)


def _decimal(value):
	result = Decimal(str(value or 0))
	if not result.is_finite():
		raise ValueError("Неприпустиме число")
	return result


def money_uk(value):
	return f"{_decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}".replace(
		",", " "
	).replace(".", ",")


def rate_uk(value):
	value = _decimal(value)
	places = min(4, max(2, -value.normalize().as_tuple().exponent))
	return f"{value:,.{places}f}".replace(",", " ").replace(".", ",")


def quantity_uk(value):
	value = _decimal(value)
	places = min(6, max(3, -value.normalize().as_tuple().exponent))
	return f"{value:.{places}f}".replace(".", ",")


def date_uk(value):
	if not value:
		return ""
	value = value if isinstance(value, date) else date.fromisoformat(str(value))
	return f"{value.day:02d} {MONTHS[value.month - 1]} {value.year} року"
