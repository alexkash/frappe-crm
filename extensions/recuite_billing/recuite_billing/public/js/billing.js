(() => {
  if (frappe._ua_billing_handlers_registered) return;
  frappe._ua_billing_handlers_registered = true;
  const api = (method, args) =>
    frappe
      .call({ method: `recuite_billing.api.${method}`, args })
      .then((r) => r.message);
  const open = (doctype, result) =>
    frappe.set_route("Form", doctype, result.name);
  async function banks(frm) {
    if (!frm.doc.issuer || frm.doc.docstatus) return;
    const issuer = await frappe.db.get_doc("UA Issuer", frm.doc.issuer);
    frm.set_df_property(
      "bank_account",
      "options",
      [""].concat(issuer.bank_accounts.map((row) => row.name)),
    );
    frm.set_df_property(
      "bank_account",
      "description",
      issuer.bank_accounts
        .map((row) =>
          frappe.utils.escape_html(
            `${row.name}: ${row.iban} · ${row.bank_name}`,
          ),
        )
        .join("<br>"),
    );
    if (!frm.doc.bank_account) {
      const selected =
        issuer.bank_accounts.find((row) => row.is_default) ||
        (issuer.bank_accounts.length === 1 && issuer.bank_accounts[0]);
      if (selected) await frm.set_value("bank_account", selected.name);
    }
  }
  function imageQueries(frm) {
    for (const kind of ["logo", "signature", "stamp"]) {
      if (frm.fields_dict[`${kind}_asset`])
        frm.set_query(`${kind}_asset`, () => ({
          filters: {
            issuer: frm.doc.issuer,
            asset_type: kind[0].toUpperCase() + kind.slice(1),
            active: 1,
          },
        }));
    }
    frm.set_query("product_code", "items", () => ({
      filters: { disabled: 0 },
    }));
  }
  async function periodDialog(frm, target) {
    const suggestion = await api("get_period_suggestion", {
      doctype: frm.doctype,
      name: frm.doc.name,
    });
    const fields = [
      {
        fieldname: "period_from",
        label: "Початок періоду",
        fieldtype: "Date",
        reqd: 1,
        default: suggestion.period_from,
      },
      {
        fieldname: "period_to",
        label: "Кінець періоду",
        fieldtype: "Date",
        reqd: 1,
        default: suggestion.period_to,
      },
    ];
    if (target === "UA Act") {
      const rows = await api("get_act_items", { invoice: frm.doc.name });
      if (!rows.length)
        return frappe.msgprint("Рахунок повністю закритий актами");
      fields.push({
        fieldname: "items",
        fieldtype: "Table",
        label: "Позиції: перевірте кількість; 0 — не включати",
        cannot_add_rows: true,
        cannot_delete_rows: true,
        in_place_edit: true,
        data: rows,
        fields: [
          { fieldname: "invoice_item", fieldtype: "Data", hidden: 1 },
          {
            fieldname: "product_name",
            fieldtype: "Data",
            label: "Послуга",
            in_list_view: 1,
            read_only: 1,
          },
          {
            fieldname: "remaining",
            fieldtype: "Float",
            label: "Залишок",
            in_list_view: 1,
            read_only: 1,
          },
          {
            fieldname: "qty",
            fieldtype: "Float",
            label: "Кількість",
            in_list_view: 1,
            precision: 6,
          },
        ],
      });
    }
    const dialog = new frappe.ui.Dialog({
      title: target === "UA Act" ? "Новий акт" : "Новий рахунок",
      fields,
      primary_action_label: "Створити чернетку",
      primary_action: async (values) => {
        dialog.disable_primary_action();
        try {
          const result =
            target === "UA Act"
              ? await api("create_act", {
                  invoice: frm.doc.name,
                  period_from: values.period_from,
                  period_to: values.period_to,
                  items: values.items
                    .filter((row) => Number(row.qty) > 0)
                    .map((row) => ({
                      invoice_item: row.invoice_item,
                      qty: row.qty,
                    })),
                })
              : await api("create_invoice", {
                  contract: frm.doc.name,
                  ...values,
                });
          dialog.hide();
          open(target, result);
        } finally {
          dialog.enable_primary_action();
        }
      },
    });
    dialog.show();
  }
  for (const doctype of ["UA Contract", "UA Invoice", "UA Act"]) {
    frappe.ui.form.on(doctype, {
      async refresh(frm) {
        imageQueries(frm);
        await banks(frm);
        if (doctype !== "UA Contract") {
          frm.set_df_property(
            doctype === "UA Act" ? "invoice" : "contract",
            "read_only",
            !frm.is_new(),
          );
          frm.set_df_property("pdf_file", "hidden", 1);
          if (!frm.is_new())
            frm.add_custom_button(
              frm.doc.docstatus ? "Архівний PDF" : "PDF чернетки",
              () => {
                if (frm.is_dirty())
                  return frappe.msgprint("Спочатку збережіть зміни");
                window.open(
                  `/api/method/recuite_billing.printing.download_pdf?doctype=${encodeURIComponent(doctype)}&name=${encodeURIComponent(frm.doc.name)}`,
                  "_blank",
                  "noopener",
                );
              },
            );
        }
        if (
          !frm.is_new() &&
          !frm.is_dirty() &&
          doctype === "UA Contract" &&
          !frm.doc.disabled &&
          frappe.model.can_create("UA Invoice")
        )
          frm.add_custom_button("Створити рахунок", () =>
            periodDialog(frm, "UA Invoice"),
          );
        if (
          doctype === "UA Invoice" &&
          frm.doc.docstatus === 1 &&
          frappe.model.can_create("UA Act")
        )
          frm.add_custom_button("Створити акт", () =>
            periodDialog(frm, "UA Act"),
          );
        if (doctype === "UA Act") {
          for (const field of [
            "product_code",
            "product_name",
            "description",
            "uom",
            "net_rate",
            "vat_mode",
            "vat_rate",
            "vat_basis",
          ])
            frm.fields_dict.items.grid.update_docfield_property(
              field,
              "read_only",
              1,
            );
          frm.fields_dict.items.grid.cannot_add_rows = true;
        }
      },
      issuer: banks,
      async contract(frm) {
        if (doctype !== "UA Invoice" || !frm.is_new() || !frm.doc.contract)
          return;
        const source = await frappe.db.get_doc("UA Contract", frm.doc.contract);
        await frm.set_value({
          issuer: source.issuer,
          organization: source.organization,
          bank_account: source.bank_account,
          act_cadence: source.act_cadence,
        });
        if (!frm.doc.items?.length) {
          for (const row of source.items)
            frm.add_child(
              "items",
              Object.fromEntries(
                [
                  "product_code",
                  "product_name",
                  "description",
                  "uom",
                  "qty",
                  "net_rate",
                  "vat_mode",
                  "vat_rate",
                  "vat_basis",
                ].map((key) => [key, row[key]]),
              ),
            );
          frm.refresh_field("items");
        }
        await frm.set_value(
          await api("get_period_suggestion", {
            doctype: source.doctype,
            name: source.name,
          }),
        );
      },
      async invoice(frm) {
        if (doctype !== "UA Act" || !frm.is_new() || !frm.doc.invoice) return;
        const source = await frappe.db.get_doc("UA Invoice", frm.doc.invoice);
        await frm.set_value({
          issuer: source.issuer,
          organization: source.organization,
          contract: source.contract,
          bank_account: source.bank_account,
        });
        frm.clear_table("items");
        const rows = await api("get_act_items", { invoice: source.name });
        for (const row of rows) frm.add_child("items", row);
        frm.refresh_field("items");
        await frm.set_value(
          await api("get_period_suggestion", {
            doctype: source.doctype,
            name: source.name,
          }),
        );
      },
    });
  }
  frappe.ui.form.on("UA Billing Item", {
    async product_code(frm, cdt, cdn) {
      if (frm.doctype === "UA Act") return;
      const row = locals[cdt][cdn];
      if (!row.product_code) return;
      const product = await frappe.db.get_doc("CRM Product", row.product_code);
      await frappe.model.set_value(cdt, cdn, {
        product_name: product.product_name,
        description: frappe.utils.strip_html(product.description || ""),
        uom: product.ua_uom || "послуга",
        net_rate: product.standard_rate || 0,
        vat_mode: product.ua_vat_mode || "Без ПДВ",
        vat_rate: product.ua_vat_rate || "0",
        vat_basis: product.ua_vat_basis || "",
      });
    },
  });
})();
