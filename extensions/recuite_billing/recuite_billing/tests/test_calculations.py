import unittest
from decimal import Decimal as D

from recuite_billing.calculations import allocate_act_items, calculate_items


class TestCalculations(unittest.TestCase):
	def test_rounds_each_line_and_ignores_supplied_totals(self):
		result = calculate_items(
			[
				{"qty": "3", "net_rate": "0.03", "vat_mode": "ПДВ", "vat_rate": "20", "net_amount": 999},
				{"qty": 1, "net_rate": "0.1", "vat_mode": "Без ПДВ"},
				{"qty": 1, "net_rate": "0.2", "vat_mode": "Без ПДВ"},
			],
			True,
		)
		self.assertEqual(result["net_total"], D("0.39"))
		self.assertEqual(result["vat_total"], D("0.02"))
		self.assertEqual(result["grand_total"], D("0.41"))
		self.assertEqual(result["items"][0]["net_amount"], D("0.09"))

	def test_rejects_invalid_money_and_quantity(self):
		for field, value in [
			("qty", "0"),
			("qty", "-1"),
			("qty", "0.0000001"),
			("qty", "NaN"),
			("net_rate", "Infinity"),
			("net_rate", "-1"),
			("net_rate", "0.00001"),
			("qty", True),
		]:
			with self.subTest(field=field, value=value), self.assertRaises(ValueError):
				calculate_items([{"qty": 1, "net_rate": 10, "vat_mode": "Без ПДВ", field: value}], False)
		with self.assertRaises(ValueError):
			calculate_items([{"qty": 1, "net_rate": "1000000000", "vat_mode": "Без ПДВ"}], False)

	def test_distinguishes_non_vat_zero_rate_and_exemption(self):
		for item, registered in [
			({"vat_mode": "ПДВ", "vat_rate": 20}, False),
			({"vat_mode": "ПДВ", "vat_rate": 0}, True),
			({"vat_mode": "Звільнено"}, True),
			({"vat_mode": "ПДВ", "vat_rate": 21}, True),
		]:
			with self.subTest(item=item), self.assertRaises(ValueError):
				calculate_items([{"qty": 1, "net_rate": 100, **item}], registered)
		result = calculate_items(
			[{"qty": 1, "net_rate": 100, "vat_mode": "ПДВ", "vat_rate": 0, "vat_basis": "Підстава"}], True
		)
		self.assertEqual(result["items"][0]["vat_mode"], "ПДВ")
		self.assertEqual(result["grand_total"], D("100.00"))

	def test_splits_vat_without_overclosing_before_last_act(self):
		for count, expected in [(3, ["0.01", "0.00", "0.01"]), (4, ["0.01", "0.00", "0.01", "0.00"])]:
			invoice = calculate_items(
				[{"name": "row-1", "qty": count, "net_rate": "0.03", "vat_mode": "ПДВ", "vat_rate": 20}], True
			)["items"]
			submitted = []
			for want in expected:
				act = allocate_act_items(invoice, submitted, [{"invoice_item": "row-1", "qty": 1}])
				self.assertEqual(act["vat_total"], D(want))
				submitted.extend(act["items"])
			self.assertEqual(sum(x["gross_amount"] for x in submitted), invoice[0]["gross_amount"])
			with self.assertRaises(ValueError):
				allocate_act_items(invoice, submitted, [{"invoice_item": "row-1", "qty": 1}])

	def test_cancelled_intermediate_act_can_be_reissued(self):
		invoice = calculate_items(
			[{"name": "r", "qty": 4, "net_rate": "0.03", "vat_mode": "ПДВ", "vat_rate": 20}], True
		)["items"]
		acts = []
		for _ in range(4):
			acts.extend(allocate_act_items(invoice, acts, [{"invoice_item": "r", "qty": 1}])["items"])
		acts.pop(1)
		replacement = allocate_act_items(invoice, acts, [{"invoice_item": "r", "qty": 1}])
		self.assertEqual(replacement["vat_total"], D("0.00"))
		self.assertEqual(sum(x["gross_amount"] for x in acts) + replacement["grand_total"], D("0.14"))

	def test_checks_each_invoice_row_and_rejects_duplicate_or_foreign_rows(self):
		invoice = calculate_items(
			[
				{"name": "a", "qty": 1, "net_rate": 10, "vat_mode": "Без ПДВ"},
				{"name": "b", "qty": 100, "net_rate": 10, "vat_mode": "Без ПДВ"},
			],
			False,
		)["items"]
		for requested in [
			[{"invoice_item": "a", "qty": 2}],
			[{"invoice_item": "foreign", "qty": 1}],
			[{"invoice_item": "a", "qty": 1}, {"invoice_item": "a", "qty": 1}],
		]:
			with self.subTest(requested=requested), self.assertRaises(ValueError):
				allocate_act_items(invoice, [], requested)

	def test_two_hundred_small_acts_remain_nonnegative_and_sum_exactly(self):
		invoice = calculate_items(
			[{"name": "r", "qty": 2, "net_rate": "0.03", "vat_mode": "ПДВ", "vat_rate": 20}], True
		)["items"]
		acts = []
		for _ in range(200):
			row = allocate_act_items(invoice, acts, [{"invoice_item": "r", "qty": "0.01"}])["items"][0]
			self.assertGreaterEqual(row["net_amount"], 0)
			self.assertGreaterEqual(row["vat_amount"], 0)
			acts.append(row)
		self.assertEqual(sum(x["gross_amount"] for x in acts), D("0.07"))
