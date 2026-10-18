import re


def validate_iban(value: str) -> str:
	value = re.sub(r"\s", "", str(value or "")).upper()
	if not re.fullmatch(r"UA\d{27}", value) or int(value[4:] + "3010" + value[2:4]) % 97 != 1:
		raise ValueError("Потрібен коректний український IBAN")
	return value


def validate_registration_code(value: str, issuer_type: str | None = None) -> str:
	value = str(value or "").strip()
	lengths = {"ФОП": {10}, "ТОВ": {8}, None: {8, 10}}
	if (
		issuer_type not in lengths
		or not re.fullmatch(r"[0-9]+", value)
		or len(value) not in lengths[issuer_type]
	):
		raise ValueError("Потрібен ЄДРПОУ (8 цифр) або РНОКПП (10 цифр)")
	return value
