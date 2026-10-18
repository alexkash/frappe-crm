import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { effectScope, reactive, nextTick } from 'vue'
import { useBillingDocumentTab } from '@/composables/useBilling'
import { documentAction } from '@/utils/billing'

const source = readFileSync(
  path.resolve(
    import.meta.dirname,
    '../../../extensions/recuite_billing/recuite_billing/public/js/billing.js',
  ),
  'utf8',
)
function setup(doctype, overrides = {}) {
  const handlers = {}
  const buttons = new Map()
  const dialogs = []
  const requests = []
  const rows = {}
  const frappe = {
    ui: {
      form: {
        on(type, events) {
          handlers[type] = events
        },
      },
      Dialog: class {
        constructor(options) {
          this.options = options
          dialogs.push(this)
        }
        show() {}
        hide() {}
        disable_primary_action() {}
        enable_primary_action() {}
      },
    },
    model: { can_create: () => true },
    utils: {
      strip_html: (s) => s,
      escape_html: (s) =>
        s
          .replaceAll('&', '&amp;')
          .replaceAll('<', '&lt;')
          .replaceAll('"', '&quot;'),
    },
    db: {
      get_doc: async () => ({
        bank_accounts: [
          { name: 'bank-1', is_default: 1, iban: 'UA-test', bank_name: 'Test' },
        ],
      }),
    },
    call: async (request) => {
      requests.push(request)
      return {
        message: request.method.endsWith('get_document_context')
          ? { related: [] }
          : request.method.endsWith('get_act_items')
            ? [
                {
                  invoice_item: 'item-1',
                  product_name: 'Service',
                  remaining: '1',
                  qty: '1',
                },
              ]
            : { period_from: '2026-10-01', period_to: '2026-10-31' },
      }
    },
    msgprint: vi.fn(),
    set_route: vi.fn(),
  }
  let dirty = false
  const frm = {
    doctype,
    doc: {
      name: 'doc-1',
      docstatus: 0,
      organization: 'company /1',
      bank_account: 'bank-1',
      ...overrides,
    },
    fields_dict: { items: { grid: { update_docfield_property() {} } } },
    is_new: () => false,
    is_dirty: () => dirty,
    set_value: async () => {
      dirty = true
    },
    set_query() {},
    set_df_property() {},
    add_custom_button: (label, fn) => buttons.set(label, fn),
    set_intro: vi.fn(),
    dashboard: { add_section: vi.fn(), clear_comment: vi.fn() },
    save: vi.fn(async () => {
      dirty = false
    }),
  }
  new Function('frappe', 'locals', source)(frappe, rows)
  return {
    frm,
    frappe,
    buttons,
    dialogs,
    requests,
    handlers,
    rows,
    refresh: () => handlers[doctype].refresh(frm),
  }
}
afterEach(() => {
  window.history.replaceState({}, '', '/')
  vi.restoreAllMocks()
})
describe('company document continuation', () => {
  it.each([
    ['A-first', 'UA Invoice', 'contract', 'UA Contract'],
    ['B-first', 'UA Invoice', 'contract', 'UA Contract'],
    ['A-first', 'UA Act', 'invoice', 'UA Invoice'],
    ['B-first', 'UA Act', 'invoice', 'UA Invoice'],
  ])(
    'ignores stale source responses in %s order for %s',
    async (order, doctype, field, sourceType) => {
      const t = setup(doctype, { [field]: 'A', items: [] })
      t.frm.is_new = () => true
      t.frm.set_value = async (values) => Object.assign(t.frm.doc, values)
      t.frm.add_child = (_, row) => t.frm.doc.items.push(row)
      t.frm.clear_table = () => {
        t.frm.doc.items = []
      }
      t.frm.refresh_field = () => {}
      const pending = {}
      t.frappe.db.get_doc = (_, name) =>
        new Promise((resolve) => {
          pending[name] = resolve
        })
      t.frappe.call = async ({ method, args }) => ({
        message: method.endsWith('get_act_items')
          ? [
              {
                invoice_item: `item-${args.invoice}`,
                product_code: `product-${args.invoice}`,
                net_rate: args.invoice === 'A' ? 10 : 20,
              },
            ]
          : {
              period_from: args.name === 'A' ? '2026-01-01' : '2026-02-01',
            },
      })
      const first = t.handlers[doctype][field](t.frm)
      t.frm.doc[field] = 'B'
      const second = t.handlers[doctype][field](t.frm)
      const contract = (name) => ({
        doctype: sourceType,
        name,
        issuer: name,
        bank_account: `bank-${name}`,
        act_cadence: name === 'A' ? 'Yearly' : 'Monthly',
        items: [
          { product_code: `product-${name}`, net_rate: name === 'A' ? 10 : 20 },
        ],
      })
      if (order === 'A-first') {
        pending.A(contract('A'))
        await first
        pending.B(contract('B'))
        await second
      } else {
        pending.B(contract('B'))
        await second
        pending.A(contract('A'))
        await first
      }
      expect(t.frm.doc).toMatchObject({
        [field]: 'B',
        issuer: 'B',
        bank_account: 'bank-B',
        period_from: '2026-02-01',
      })
      if (doctype === 'UA Invoice')
        expect(t.frm.doc.act_cadence).toBe('Monthly')
      expect(t.frm.doc.items).toHaveLength(1)
      expect(t.frm.doc.items[0]).toMatchObject({
        product_code: 'product-B',
        net_rate: 20,
      })
    },
  )
  it.each(['changed', 'deleted'])(
    'ignores stale product responses for a %s row',
    async (state) => {
      const t = setup('UA Invoice')
      const row = { name: 'line-1', product_code: 'A', net_rate: 20 }
      t.rows['UA Billing Item'] = { 'line-1': row }
      t.frm.doc.items = [row]
      t.frappe.model.set_value = async (_, name, values) =>
        Object.assign(t.rows['UA Billing Item'][name], values)
      let resolve
      t.frappe.db.get_doc = () =>
        new Promise((done) => {
          resolve = done
        })
      const pending = t.handlers['UA Billing Item'].product_code(
        t.frm,
        'UA Billing Item',
        'line-1',
      )
      if (state === 'changed') row.product_code = 'B'
      else t.frm.doc.items = []
      resolve({ product_name: 'Product A', standard_rate: 10, description: '' })
      await pending
      expect(row.net_rate).toBe(20)
      expect(row.product_name).toBeUndefined()
    },
  )
  it('still populates the currently selected product', async () => {
    const t = setup('UA Invoice')
    const row = { name: 'line-1', product_code: 'A' }
    t.rows['UA Billing Item'] = { 'line-1': row }
    t.frm.doc.items = [row]
    t.frappe.model.set_value = async (_, name, values) =>
      Object.assign(t.rows['UA Billing Item'][name], values)
    t.frappe.db.get_doc = async () => ({
      product_name: 'Product A',
      standard_rate: 10,
      description: 'Service',
    })
    await t.handlers['UA Billing Item'].product_code(
      t.frm,
      'UA Billing Item',
      'line-1',
    )
    expect(row).toMatchObject({
      product_code: 'A',
      product_name: 'Product A',
      net_rate: 10,
      description: 'Service',
      vat_mode: 'Без ПДВ',
    })
  })
  it('ignores a delayed bank response after the issuer changes on the same form', async () => {
    const t = setup('UA Contract', { issuer: 'A', bank_account: '' })
    t.frm.set_value = async (_, value) => {
      t.frm.doc.bank_account = value
    }
    const pending = {}
    t.frappe.db.get_doc = (_, name) =>
      new Promise((resolve) => {
        pending[name] = resolve
      })
    const first = t.handlers['UA Contract'].issuer(t.frm)
    t.frm.doc.issuer = 'B'
    const second = t.handlers['UA Contract'].issuer(t.frm)
    pending.A({
      bank_accounts: [
        { name: 'bank-A', is_default: 1, iban: 'A', bank_name: 'A' },
      ],
    })
    await first
    pending.B({
      bank_accounts: [
        { name: 'bank-B', is_default: 1, iban: 'B', bank_name: 'B' },
      ],
    })
    await second
    expect(t.frm.doc.bank_account).toBe('bank-B')
  })
  it('selects Documents after delayed capabilities, including the mobile Details fallback', async () => {
    for (const fallback of ['deals', 'details']) {
      const scope = effectScope()
      const billing = reactive({ data: null })
      const route = reactive({ query: { tab: 'documents' } })
      const selected = scope.run(() =>
        useBillingDocumentTab(billing, route, fallback),
      )
      expect(selected.value).toBe(fallback)
      billing.data = { enabled: true, can_read: true }
      await nextTick()
      expect(selected.value).toBe('documents')
      selected.value = fallback
      await nextTick()
      expect(selected.value).toBe(fallback)
      scope.stop()
    }
  })
  it('discards relationships returned after navigating to a different document', async () => {
    const t = setup('UA Contract')
    let resolve
    t.frappe.call = () =>
      new Promise((done) => {
        resolve = done
      })
    const pending = t.refresh()
    await Promise.resolve()
    t.frm.doc = { ...t.frm.doc, name: 'contract-B', organization: 'company-B' }
    resolve({
      message: {
        related: [{ doctype: 'UA Invoice', name: 'invoice-A', docstatus: 0 }],
      },
    })
    await pending
    expect(t.frm.dashboard.add_section).not.toHaveBeenCalled()
  })
  it('offers invoice creation for an active contract and hides it for closed contracts or readers', () => {
    expect(
      documentAction(
        'contracts',
        { name: 'c1', disabled: 0 },
        { create: { 'UA Invoice': true } },
      ),
    ).toEqual({ label: 'Створити рахунок', action: 'invoice' })
    expect(
      documentAction(
        'contracts',
        { disabled: 1 },
        { create: { 'UA Invoice': true } },
      ),
    ).toBeNull()
    expect(
      documentAction('contracts', { disabled: 0 }, { create: {} }),
    ).toBeNull()
    expect(
      documentAction(
        'invoices',
        { docstatus: 1 },
        { create: { 'UA Act': true } },
      ),
    ).toEqual({ label: 'Створити акт', action: 'act' })
    expect(
      documentAction(
        'invoices',
        { docstatus: 0 },
        { create: { 'UA Act': true } },
      ),
    ).toEqual({ label: 'Продовжити оформлення', action: null })
    expect(
      documentAction(
        'invoices',
        { docstatus: 2 },
        { create: { 'UA Act': true } },
      ),
    ).toBeNull()
  })
  it('keeps contract continuation visible when default bank selection makes the saved form dirty', async () => {
    const t = setup('UA Contract', { issuer: 'issuer-1', bank_account: '' })
    await t.refresh()
    expect([...t.buttons.keys()]).toContain('Створити рахунок')
    await t.buttons.get('Створити рахунок')()
    expect(t.dialogs).toHaveLength(0)
    expect(t.frappe.msgprint).toHaveBeenCalled()
  })
  it('opens the period dialog from a company row without creating anything until confirmation', async () => {
    window.history.replaceState(
      {},
      '',
      '/app/ua-contract/doc-1?billing_action=invoice',
    )
    const t = setup('UA Contract')
    await t.refresh()
    expect(t.dialogs).toHaveLength(1)
    expect(t.dialogs[0].options.title).toBe('Новий рахунок')
    expect(t.requests.some((r) => r.method.endsWith('create_invoice'))).toBe(
      false,
    )
    await t.refresh()
    expect(t.dialogs).toHaveLength(1)
  })
  it('explains why a draft invoice cannot yet create an act', async () => {
    const t = setup('UA Invoice')
    await t.refresh()
    expect(t.frm.set_intro).toHaveBeenCalledWith(
      expect.stringContaining('випустіть рахунок'),
      'blue',
    )
    expect(t.buttons.has('Створити акт')).toBe(false)
  })
  it('creates the next act from a submitted invoice and keeps draft creation explicit', async () => {
    window.history.replaceState(
      {},
      '',
      '/app/ua-invoice/doc-1?billing_action=act',
    )
    const t = setup('UA Invoice', { docstatus: 1 })
    await t.refresh()
    expect(t.dialogs).toHaveLength(1)
    expect(t.dialogs[0].options.title).toBe('Новий акт')
    expect(t.requests.some((r) => r.method.endsWith('create_act'))).toBe(false)
  })
  it.each([
    ['UA Contract', 0, 'invoice', 'UA Invoice', 'create_invoice'],
    ['UA Invoice', 1, 'act', 'UA Act', 'create_act'],
  ])(
    'allows a manual remaining period for %s when no dates are suggested',
    async (doctype, docstatus, action, target, method) => {
      window.history.replaceState(
        {},
        '',
        `/app/source/doc-1?billing_action=${action}`,
      )
      const t = setup(doctype, { docstatus })
      t.frappe.call = async (request) => {
        t.requests.push(request)
        if (request.method.endsWith('get_document_context'))
          return { message: { related: [] } }
        if (request.method.endsWith('get_period_suggestion'))
          return { message: {} }
        if (request.method.endsWith('get_act_items'))
          return {
            message: [
              {
                invoice_item: 'item-1',
                product_name: 'Service',
                remaining: '6',
                qty: '6',
              },
            ],
          }
        if (request.method === `recuite_billing.api.${method}`)
          return { message: { name: 'remaining-draft', existing: false } }
        throw new Error(`Unexpected request: ${request.method}`)
      }
      await t.refresh()
      expect(t.dialogs).toHaveLength(1)
      const fields = t.dialogs[0].options.fields
      for (const name of ['period_from', 'period_to']) {
        expect(fields.find((field) => field.fieldname === name)).toMatchObject({
          reqd: 1,
          default: undefined,
        })
      }
      expect(
        t.requests.some((request) => request.method.endsWith(method)),
      ).toBe(false)
      const dates = { period_from: '2026-01-16', period_to: '2026-01-31' }
      const values =
        action === 'act'
          ? { ...dates, items: [{ invoice_item: 'item-1', qty: '6' }] }
          : dates
      await t.dialogs[0].options.primary_action(values)
      expect(
        t.requests.filter(
          (request) => request.method === `recuite_billing.api.${method}`,
        ),
      ).toEqual([
        {
          method: `recuite_billing.api.${method}`,
          args: {
            [action === 'act' ? 'invoice' : 'contract']: 'doc-1',
            ...values,
          },
        },
      ])
      expect(t.frappe.set_route).toHaveBeenCalledWith(
        'Form',
        target,
        'remaining-draft',
      )
    },
  )
  it('still blocks an act when no invoice quantities remain and no dates are suggested', async () => {
    const t = setup('UA Invoice', { docstatus: 1 })
    t.frappe.call = async ({ method }) => ({
      message: method.endsWith('get_document_context')
        ? { related: [] }
        : method.endsWith('get_period_suggestion')
          ? {}
          : [],
    })
    await t.refresh()
    await t.buttons.get('Створити акт')()
    expect(t.dialogs).toHaveLength(0)
    expect(t.frappe.msgprint).toHaveBeenCalledWith(
      'Рахунок повністю закритий актами',
    )
  })
  it('does not let an unrelated requested action bypass document state', async () => {
    window.history.replaceState(
      {},
      '',
      '/app/ua-invoice/doc-1?billing_action=act',
    )
    const t = setup('UA Invoice')
    await t.refresh()
    expect(t.dialogs).toHaveLength(0)
  })
  it('shows linked documents using escaped labels, with a return to the real company', async () => {
    const t = setup('UA Contract')
    t.frappe.call = async () => ({
      message: {
        related: [
          {
            doctype: 'UA Invoice',
            name: 'i/#',
            print_number: '<invoice>',
            docstatus: 1,
            period_from: '2026-10-01',
            period_to: '2026-10-31',
          },
        ],
      },
    })
    await t.refresh()
    const html = t.frm.dashboard.add_section.mock.calls
      .map((args) => args[0])
      .join('')
    expect(html).toContain('/app/ua-invoice/i%2F%23')
    expect(html).toContain('&lt;invoice>')
    expect(html).not.toContain('><invoice>')
    expect(html).toContain('/crm/organizations/company%20%2F1?tab=documents')
  })
})
