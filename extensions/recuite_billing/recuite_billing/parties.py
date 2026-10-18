"""Plain legal-requisite snapshots, independent of Frappe and mutable source records."""

import re

from recuite_billing.validations import validate_iban, validate_registration_code

FIELDS = (
	"legal_name",
	"registration_code",
	"legal_address",
	"phone",
	"vat_number",
	"income_tax_note",
	"signatory",
	"signatory_position",
)


def _party(record, *, customer=False, require_complete=False, payer=False):
	prefix = "ua_" if customer else ""
	result = {key: str(record.get(prefix + key) or "").strip() for key in FIELDS}
	result["name"] = record.get("name")
	result["vat_registered"] = bool(record.get(prefix + "vat_registered"))
	result["issuer_type"] = record.get("issuer_type", "") if not customer else ""
	if not require_complete and not result["legal_name"]:
		result["legal_name"] = record.get("organization_name") or record.get("name") or ""
	if require_complete:
		required = (
			("legal_name", "registration_code")
			if payer
			else ("legal_name", "registration_code", "legal_address", "signatory")
		)
		missing = [key for key in required if not result[key]]
		if missing:
			labels = {
				"legal_name": "юридичне найменування",
				"registration_code": "ЄДРПОУ / РНОКПП",
				"legal_address": "юридична адреса",
				"signatory": "ПІБ підписанта",
			}
			party = "Платник" if payer else "Замовник" if customer else "Виконавець"
			raise ValueError(party + ": заповніть реквізити — " + ", ".join(labels[key] for key in missing))
		result["registration_code"] = validate_registration_code(
			result["registration_code"], None if customer else record.get("issuer_type")
		)
		if result["vat_registered"] and not re.fullmatch(r"[0-9]{12}", result["vat_number"]):
			raise ValueError("Для платника ПДВ потрібен ІПН із 12 цифр")
	if customer:
		result.update(
			iban=str(record.get("ua_iban") or "").strip(),
			bank_name=str(record.get("ua_bank_name") or "").strip(),
			bank_mfo=str(record.get("ua_bank_mfo") or "").strip(),
		)
		if require_complete and result["iban"]:
			result["iban"] = validate_iban(result["iban"])
			result["bank_mfo"] = result["iban"][4:10]
	return result


def make_party_snapshot(
	issuer: dict,
	customer: dict,
	bank_account: str | None = None,
	*,
	payer: dict | None = None,
	require_complete=False,
) -> dict:
	accounts = issuer.get("bank_accounts") or []
	if bank_account:
		selected = next((row for row in accounts if row.get("name") == bank_account), None)
		if selected is None:
			raise ValueError("Банківський рахунок не належить виконавцю")
	else:
		selected = next((row for row in accounts if row.get("is_default")), None)
		if selected is None and len(accounts) == 1:
			selected = accounts[0]
	bank = {
		key: str((selected or {}).get(key) or "").strip() for key in ("name", "iban", "bank_name", "bank_mfo")
	}
	if require_complete and (not bank["iban"] or not bank["bank_name"]):
		raise ValueError("Оберіть банківський рахунок виконавця з IBAN і назвою банку")
	if bank["iban"]:
		bank["iban"] = validate_iban(bank["iban"])
		if bank["bank_mfo"] and bank["bank_mfo"] != bank["iban"][4:10]:
			raise ValueError("МФО не відповідає IBAN")
		bank["bank_mfo"] = bank["iban"][4:10]
	customer_party = _party(customer, customer=True, require_complete=require_complete)
	same = payer is None or payer.get("name") == customer.get("name")
	return {
		"currency": "UAH",
		"issuer": _party(issuer, require_complete=require_complete),
		"customer": customer_party,
		"bank": bank,
		"payer_is_customer": same,
		"payer": dict(customer_party)
		if same
		else _party(payer, customer=True, payer=True, require_complete=require_complete),
	}
