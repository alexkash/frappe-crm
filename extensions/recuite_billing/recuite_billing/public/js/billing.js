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
    const doc = frm.doc;
    if (!doc.issuer || doc.docstatus) return;
    const selectedIssuer = doc.issuer;
    const issuer = await frappe.db.get_doc("UA Issuer", selectedIssuer);
    if (frm.doc !== doc || doc.issuer !== selectedIssuer) return;
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
    if (frm.is_dirty()) return frappe.msgprint(__("Спочатку збережіть зміни"));
    const doc = frm.doc;
    const suggestion = await api("get_period_suggestion", {
      doctype: frm.doctype,
      name: doc.name,
    });
    if (frm.doc !== doc) return;
    const fields = [
      {
        fieldname: "period_from",
        label: __("Початок періоду"),
        fieldtype: "Date",
        reqd: 1,
        default: suggestion.period_from,
      },
      {
        fieldname: "period_to",
        label: __("Кінець періоду"),
        fieldtype: "Date",
        reqd: 1,
        default: suggestion.period_to,
      },
    ];
    if (target === "UA Act") {
      const rows = await api("get_act_items", { invoice: doc.name });
      if (frm.doc !== doc) return;
      if (!rows.length)
        return frappe.msgprint(__("Рахунок повністю закритий актами"));
      fields.push({
        fieldname: "items",
        fieldtype: "Table",
        label: __("Позиції: перевірте кількість; 0 — не включати"),
        cannot_add_rows: true,
        cannot_delete_rows: true,
        in_place_edit: true,
        data: rows,
        fields: [
          { fieldname: "invoice_item", fieldtype: "Data", hidden: 1 },
          {
            fieldname: "product_name",
            fieldtype: "Data",
            label: __("Послуга"),
            in_list_view: 1,
            read_only: 1,
          },
          {
            fieldname: "remaining",
            fieldtype: "Float",
            label: __("Залишок"),
            in_list_view: 1,
            read_only: 1,
          },
          {
            fieldname: "qty",
            fieldtype: "Float",
            label: __("Кількість"),
            in_list_view: 1,
            precision: 6,
          },
        ],
      });
    }
    const dialog = new frappe.ui.Dialog({
      title: target === "UA Act" ? __("Новий акт") : __("Новий рахунок"),
      fields,
      primary_action_label: __("Створити чернетку"),
      primary_action: async (values) => {
        if (frm.doc !== doc || frm.is_dirty())
          return frappe.msgprint(
            __("Документ змінився. Закрийте діалог і повторіть дію."),
          );
        dialog.disable_primary_action();
        try {
          const result =
            target === "UA Act"
              ? await api("create_act", {
                  invoice: doc.name,
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
                  contract: doc.name,
                  ...values,
                });
          dialog.hide();
          if (result.existing)
            frappe.msgprint(
              __("Документ за цей період уже існує. Відкриваємо його."),
            );
          open(target, result);
        } finally {
          dialog.enable_primary_action();
        }
      },
    });
    dialog.show();
  }
  const labels = {
    "UA Contract": "Договір",
    "UA Invoice": "Рахунок",
    "UA Act": "Акт",
  };
  const documentURL = (doctype, name) =>
    `/app/${doctype.toLowerCase().replaceAll(" ", "-")}/${encodeURIComponent(name)}`;
  async function context(frm, isCurrent) {
    if (frm.is_new()) return;
    const data = await api("get_document_context", {
      doctype: frm.doctype,
      name: frm.doc.name,
    });
    if (!isCurrent()) return;
    const escape = frappe.utils.escape_html;
    const kind = {
      "UA Contract": "contracts",
      "UA Invoice": "invoices",
      "UA Act": "acts",
    }[frm.doctype];
    const company = frm.doc.organization
      ? `<a href="/crm/organizations/${encodeURIComponent(frm.doc.organization)}?tab=documents&kind=${kind}">До компанії → Документи</a>`
      : "";
    const rows = data.related
      .map((row) => {
        const status =
          row.doctype === "UA Contract"
            ? ""
            : ["Чернетка", "Випущено", "Скасовано"][row.docstatus] || "";
        const period = row.period_from
          ? ` · ${escape(row.period_from)} — ${escape(row.period_to)}`
          : "";
        return `<li class="py-2"><a href="${documentURL(row.doctype, row.name)}">${labels[row.doctype]} ${escape(row.print_number || row.contract_number || row.name)}</a> · ${status}${period}</li>`;
      })
      .join("");
    const more = (data.more || [])
      .map(
        (row) =>
          `<a class="mr-3" href="/app/${row.doctype.toLowerCase().replaceAll(" ", "-")}?${row.field}=${encodeURIComponent(row.value)}">Усі: ${labels[row.doctype]}</a>`,
      )
      .join("");
    frm.dashboard.add_section(
      `${company}<ul class="list-unstyled mb-0">${rows || '<li class="py-2 text-muted">Пов’язаних документів поки немає</li>'}</ul>${more}`,
      "Пов’язані документи",
    );
  }
  async function requestedAction(frm) {
    const url = new URL(window.location.href);
    const action = url.searchParams.get("billing_action");
    if (!action) return;
    url.searchParams.delete("billing_action");
    window.history.replaceState(window.history.state, "", url);
    if (frm.is_new()) return;
    if (
      action === "invoice" &&
      frm.doctype === "UA Contract" &&
      !frm.doc.disabled &&
      frappe.model.can_create("UA Invoice")
    )
      return periodDialog(frm, "UA Invoice");
    if (
      action === "act" &&
      frm.doctype === "UA Invoice" &&
      frm.doc.docstatus === 1 &&
      frappe.model.can_create("UA Act")
    )
      return periodDialog(frm, "UA Act");
  }
  for (const doctype of ["UA Contract", "UA Invoice", "UA Act"]) {
    frappe.ui.form.on(doctype, {
      async refresh(frm) {
        const doc = frm.doc;
        const refresh = {};
        frm._ua_billing_refresh = refresh;
        const isCurrent = () =>
          frm.doc === doc && frm._ua_billing_refresh === refresh;
        imageQueries(frm);
        if (doctype !== "UA Contract") {
          frm.set_df_property(
            doctype === "UA Act" ? "invoice" : "contract",
            "read_only",
            !frm.is_new(),
          );
          frm.set_df_property("pdf_file", "hidden", 1);
          if (!frm.is_new())
            frm.add_custom_button(
              frm.doc.docstatus ? __("Архівний PDF") : __("PDF чернетки"),
              () => {
                if (frm.is_dirty())
                  return frappe.msgprint(__("Спочатку збережіть зміни"));
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
          doctype === "UA Contract" &&
          !frm.doc.disabled &&
          frappe.model.can_create("UA Invoice")
        )
          frm.add_custom_button(__("Створити рахунок"), () =>
            periodDialog(frm, "UA Invoice"),
          );
        if (
          doctype === "UA Invoice" &&
          frm.doc.docstatus === 1 &&
          frappe.model.can_create("UA Act")
        )
          frm.add_custom_button(__("Створити акт"), () =>
            periodDialog(frm, "UA Act"),
          );
        if (doctype === "UA Invoice" && frm.doc.docstatus === 0)
          frm.set_intro(
            __("Щоб створити акт, спочатку збережіть і випустіть рахунок."),
            "blue",
          );
        if (doctype === "UA Contract" && frm.doc.disabled)
          frm.set_intro(
            __("Договір закритий. Перегляньте пов’язані рахунки й акти нижче."),
            "blue",
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
        await banks(frm);
        if (!isCurrent()) return;
        await context(frm, isCurrent);
        if (isCurrent()) await requestedAction(frm);
      },
      issuer: banks,
      async contract(frm) {
        if (doctype !== "UA Invoice" || !frm.is_new() || !frm.doc.contract)
          return;
        const doc = frm.doc;
        const selectedContract = doc.contract;
        const isCurrent = () =>
          frm.doc === doc && doc.contract === selectedContract;
        const source = await frappe.db.get_doc("UA Contract", selectedContract);
        if (!isCurrent()) return;
        await frm.set_value({
          issuer: source.issuer,
          organization: source.organization,
          bank_account: source.bank_account,
          act_cadence: source.act_cadence,
        });
        if (!isCurrent()) return;
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
        const period = await api("get_period_suggestion", {
          doctype: source.doctype,
          name: source.name,
        });
        if (isCurrent()) await frm.set_value(period);
      },
      async invoice(frm) {
        if (doctype !== "UA Act" || !frm.is_new() || !frm.doc.invoice) return;
        const doc = frm.doc;
        const selectedInvoice = doc.invoice;
        const isCurrent = () =>
          frm.doc === doc && doc.invoice === selectedInvoice;
        const source = await frappe.db.get_doc("UA Invoice", selectedInvoice);
        if (!isCurrent()) return;
        await frm.set_value({
          issuer: source.issuer,
          organization: source.organization,
          contract: source.contract,
          bank_account: source.bank_account,
        });
        if (!isCurrent()) return;
        const rows = await api("get_act_items", { invoice: source.name });
        if (!isCurrent()) return;
        frm.clear_table("items");
        for (const row of rows) frm.add_child("items", row);
        frm.refresh_field("items");
        const period = await api("get_period_suggestion", {
          doctype: source.doctype,
          name: source.name,
        });
        if (isCurrent()) await frm.set_value(period);
      },
    });
  }
  frappe.ui.form.on("UA Billing Item", {
    async product_code(frm, cdt, cdn) {
      if (frm.doctype === "UA Act") return;
      const doc = frm.doc;
      const row = locals[cdt]?.[cdn];
      if (!row?.product_code) return;
      const selectedProduct = row.product_code;
      const product = await frappe.db.get_doc("CRM Product", selectedProduct);
      if (
        frm.doc !== doc ||
        locals[cdt]?.[cdn] !== row ||
        row.product_code !== selectedProduct ||
        !doc.items?.some((item) => item.name === cdn)
      )
        return;
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
