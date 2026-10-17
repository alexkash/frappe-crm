"""UAH calculations shared by document validation and partial acceptance acts."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999.99")


def number(value, places=6, *, positive=False):
	try:
		if isinstance(value, bool):
			raise ValueError("Boolean is not a number")
		result = Decimal(str(value))
		if not result.is_finite() or result < 0 or (positive and not result):
			raise ValueError("Number must be finite and nonnegative")
		if result > MAX_AMOUNT or result != result.quantize(Decimal(1).scaleb(-places)):
			raise ValueError("Number exceeds supported precision or amount")
		return result
	except (InvalidOperation, TypeError) as exc:
		raise ValueError("Invalid number") from exc


def money(value):
	return value.quantize(CENT, rounding=ROUND_HALF_UP)


def totals(items):
	net = sum((row["net_amount"] for row in items), Decimal(0))
	vat = sum((row["vat_amount"] for row in items), Decimal(0))
	if net + vat > MAX_AMOUNT:
		raise ValueError("Document amount exceeds supported maximum")
	return {"items": items, "net_total": money(net), "vat_total": money(vat), "grand_total": money(net + vat)}


def calculate_items(items: list[dict], issuer_vat_registered: bool) -> dict:
	if not items:
		raise ValueError("At least one item is required")
	result = []
	for source in items:
		row = dict(source)
		qty = number(row.get("qty"), positive=True)
		rate = number(row.get("net_rate"), 4)
		mode = row.get("vat_mode") or "Без ПДВ"
		vat_rate = number(row.get("vat_rate") or 0, 2)
		if mode not in {"Без ПДВ", "ПДВ", "Звільнено"}:
			raise ValueError("Unsupported VAT mode")
		if not issuer_vat_registered and mode != "Без ПДВ":
			raise ValueError("Issuer is not registered for VAT")
		if mode == "ПДВ":
			if vat_rate not in {Decimal(x) for x in (0, 7, 14, 20)}:
				raise ValueError("Unsupported VAT rate")
		elif vat_rate:
			raise ValueError("VAT rate must be zero for this mode")
		if (mode == "Звільнено" or (mode == "ПДВ" and not vat_rate)) and not str(
			row.get("vat_basis") or ""
		).strip():
			raise ValueError("A VAT basis is required")
		net = money(qty * rate)
		vat = money(net * vat_rate / 100) if mode == "ПДВ" else Decimal("0.00")
		row.update(
			qty=qty,
			net_rate=rate,
			vat_mode=mode,
			vat_rate=vat_rate,
			net_amount=net,
			vat_amount=vat,
			gross_amount=net + vat,
		)
		result.append(row)
	return totals(result)


def allocate_act_items(
	invoice_items: list[dict], submitted_items: list[dict], requested_items: list[dict]
) -> dict:
	if not requested_items:
		raise ValueError("At least one act item is required")
	invoice = {row["name"]: row for row in invoice_items}
	if len(invoice) != len(invoice_items):
		raise ValueError("Duplicate invoice item")
	used = {name: {key: Decimal(0) for key in ("qty", "net_amount", "vat_amount")} for name in invoice}
	for row in submitted_items:
		name = row.get("invoice_item")
		if name not in used:
			raise ValueError("Unknown submitted invoice item")
		for key in used[name]:
			used[name][key] += number(row.get(key, 0), 6 if key == "qty" else 2)
	result, seen = [], set()
	for requested in requested_items:
		if not isinstance(requested, dict):
			raise ValueError("Позиція акта має містити рядок рахунку та кількість")
		name = requested.get("invoice_item")
		if not isinstance(name, str) or name not in invoice or name in seen:
			raise ValueError("Unknown or duplicate invoice item")
		seen.add(name)
		source, previous = invoice[name], used[name]
		qty = number(requested.get("qty"), positive=True)
		total_qty = number(source["qty"], positive=True)
		cumulative = previous["qty"] + qty
		if cumulative > total_qty:
			raise ValueError("Act exceeds the remaining invoice quantity")
		row = {**source, "invoice_item": name, "qty": qty}
		row.pop("name", None)
		for key in ("net_amount", "vat_amount"):
			total = number(source[key], 2)
			remaining = total - previous[key]
			if remaining < 0:
				raise ValueError("Submitted acts exceed the invoice amount")
			target = money(total * cumulative / total_qty)
			row[key] = (
				remaining
				if cumulative == total_qty
				else min(remaining, max(Decimal(0), target - previous[key]))
			)
		row["gross_amount"] = row["net_amount"] + row["vat_amount"]
		row["rounding_adjustment"] = row["net_amount"] - money(qty * number(source["net_rate"], 4))
		result.append(row)
	return totals(result)
