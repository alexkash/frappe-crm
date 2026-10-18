"""Ukrainian UAH words, independent of the user's interface language."""

from decimal import Decimal

from recuite_billing.calculations import number

ONES = ("", "один", "два", "три", "чотири", "п'ять", "шість", "сім", "вісім", "дев'ять")
TEENS = (
	"десять",
	"одинадцять",
	"дванадцять",
	"тринадцять",
	"чотирнадцять",
	"п'ятнадцять",
	"шістнадцять",
	"сімнадцять",
	"вісімнадцять",
	"дев'ятнадцять",
)
TENS = (
	"",
	"",
	"двадцять",
	"тридцять",
	"сорок",
	"п'ятдесят",
	"шістдесят",
	"сімдесят",
	"вісімдесят",
	"дев'яносто",
)
HUNDREDS = (
	"",
	"сто",
	"двісті",
	"триста",
	"чотириста",
	"п'ятсот",
	"шістсот",
	"сімсот",
	"вісімсот",
	"дев'ятсот",
)


def _ending(value, forms):
	return forms[2 if 11 <= value % 100 <= 14 else 0 if value % 10 == 1 else 1 if 2 <= value % 10 <= 4 else 2]


def _group(value, female):
	words = [HUNDREDS[value // 100]] if value >= 100 else []
	value %= 100
	if 10 <= value < 20:
		words.append(TEENS[value - 10])
	else:
		if value >= 20:
			words.append(TENS[value // 10])
		if value % 10:
			unit = value % 10
			words.append(("одна" if unit == 1 else "дві") if female and unit in (1, 2) else ONES[unit])
	return words


def amount_in_words_uk(amount: Decimal) -> str:
	amount = number(amount, 2)
	whole = int(amount)
	kopecks = int((amount - whole) * 100)
	words = []
	for divisor, forms, female in [
		(1000000, ("мільйон", "мільйони", "мільйонів"), False),
		(1000, ("тисяча", "тисячі", "тисяч"), True),
	]:
		group = whole // divisor % 1000
		if group:
			words.extend([*_group(group, female), _ending(group, forms)])
	words.extend(_group(whole % 1000, True))
	if not whole:
		words.append("нуль")
	words.extend(
		[
			_ending(whole, ("гривня", "гривні", "гривень")),
			f"{kopecks:02d}",
			_ending(kopecks, ("копійка", "копійки", "копійок")),
		]
	)
	return " ".join(words).capitalize()
