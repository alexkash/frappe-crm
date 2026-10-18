import { afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { effectScope, reactive, nextTick } from 'vue'
import { useBillingDocumentTab } from '@/composables/useBilling'
import { documentAction } from '@/utils/billing'

const source = readFileSync(path.resolve(import.meta.dirname, '../../../extensions/recuite_billing/recuite_billing/public/js/billing.js'), 'utf8')
function setup(doctype, overrides = {}) {
  const handlers = {}
  const buttons = new Map()
  const dialogs = []
  const requests = []
  const frappe = {
    ui: { form: { on(type, events) { handlers[type] = events } }, Dialog: class {
      constructor(options) { this.options = options; dialogs.push(this) }
      show() {} hide() {} disable_primary_action() {} enable_primary_action() {}
    } },
    model: { can_create: () => true },
    utils: { escape_html: (s) => s.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('"', '&quot;') },
    db: { get_doc: async () => ({ bank_accounts: [{name: 'bank-1', is_default: 1, iban: 'UA-test', bank_name: 'Test'}] }) },
    call: async (request) => { requests.push(request); return { message: request.method.endsWith('get_document_context') ? { related: [] } : request.method.endsWith('get_act_items') ? [{invoice_item: 'item-1', product_name: 'Service', remaining: '1', qty: '1'}] : {period_from: '2026-10-01', period_to: '2026-10-31'} } },
    msgprint: vi.fn(), set_route: vi.fn(),
  }
  let dirty = false
  const frm = {
    doctype,
    doc: { name: 'doc-1', docstatus: 0, organization: 'company /1', bank_account: 'bank-1', ...overrides },
    fields_dict: { items: {grid: { update_docfield_property() {} }} },
    is_new: () => false, is_dirty: () => dirty,
    set_value: async () => { dirty = true }, set_query() {}, set_df_property() {},
    add_custom_button: (label, fn) => buttons.set(label, fn),
    set_intro: vi.fn(), dashboard: { add_section: vi.fn(), clear_comment: vi.fn() },
    save: vi.fn(async () => { dirty = false }),
  }
  new Function('frappe', source)(frappe)
  return {frm, frappe, buttons, dialogs, requests, refresh: () => handlers[doctype].refresh(frm)}
}
afterEach(() => { window.history.replaceState({}, '', '/'); vi.restoreAllMocks() })
describe('company document continuation', () => {
  it('selects Documents after delayed capabilities, including the mobile Details fallback', async () => {
    for (const fallback of ['deals', 'details']) {
      const scope = effectScope()
      const billing = reactive({ data: null })
      const route = reactive({ query: { tab: 'documents' } })
      const selected = scope.run(() => useBillingDocumentTab(billing, route, fallback))
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
    t.frappe.call = () => new Promise(done => { resolve = done })
    const pending = t.refresh()
    await Promise.resolve()
    t.frm.doc = { ...t.frm.doc, name:'contract-B', organization:'company-B' }
    resolve({message:{related:[{doctype:'UA Invoice',name:'invoice-A',docstatus:0}]}})
    await pending
    expect(t.frm.dashboard.add_section).not.toHaveBeenCalled()
  })
  it('offers invoice creation for an active contract and hides it for closed contracts or readers', () => {
    expect(documentAction('contracts', {name:'c1', disabled:0}, {create:{'UA Invoice':true}})).toEqual({label:'Створити рахунок', action:'invoice'})
    expect(documentAction('contracts', {disabled:1}, {create:{'UA Invoice':true}})).toBeNull()
    expect(documentAction('contracts', {disabled:0}, {create:{}})).toBeNull()
    expect(documentAction('invoices', {docstatus:1}, {create:{'UA Act':true}})).toEqual({label:'Створити акт', action:'act'})
    expect(documentAction('invoices', {docstatus:0}, {create:{'UA Act':true}})).toEqual({label:'Продовжити оформлення', action:null})
    expect(documentAction('invoices', {docstatus:2}, {create:{'UA Act':true}})).toBeNull()
  })
  it('keeps contract continuation visible when default bank selection makes the saved form dirty', async () => {
    const t = setup('UA Contract', {issuer:'issuer-1', bank_account:''})
    await t.refresh()
    expect([...t.buttons.keys()]).toContain('Створити рахунок')
    await t.buttons.get('Створити рахунок')()
    expect(t.dialogs).toHaveLength(0)
    expect(t.frappe.msgprint).toHaveBeenCalled()
  })
  it('opens the period dialog from a company row without creating anything until confirmation', async () => {
    window.history.replaceState({}, '', '/app/ua-contract/doc-1?billing_action=invoice')
    const t = setup('UA Contract')
    await t.refresh()
    expect(t.dialogs).toHaveLength(1)
    expect(t.dialogs[0].options.title).toBe('Новий рахунок')
    expect(t.requests.some(r => r.method.endsWith('create_invoice'))).toBe(false)
    await t.refresh()
    expect(t.dialogs).toHaveLength(1)
  })
  it('explains why a draft invoice cannot yet create an act', async () => {
    const t = setup('UA Invoice')
    await t.refresh()
    expect(t.frm.set_intro).toHaveBeenCalledWith(expect.stringContaining('випустіть рахунок'), 'blue')
    expect(t.buttons.has('Створити акт')).toBe(false)
  })
  it('creates the next act from a submitted invoice and keeps draft creation explicit', async () => {
    window.history.replaceState({}, '', '/app/ua-invoice/doc-1?billing_action=act')
    const t = setup('UA Invoice', {docstatus:1})
    await t.refresh()
    expect(t.dialogs).toHaveLength(1)
    expect(t.dialogs[0].options.title).toBe('Новий акт')
    expect(t.requests.some(r => r.method.endsWith('create_act'))).toBe(false)
  })
  it('does not let an unrelated requested action bypass document state', async () => {
    window.history.replaceState({}, '', '/app/ua-invoice/doc-1?billing_action=act')
    const t = setup('UA Invoice')
    await t.refresh()
    expect(t.dialogs).toHaveLength(0)
  })
  it('shows linked documents using escaped labels, with a return to the real company', async () => {
    const t = setup('UA Contract')
    t.frappe.call = async () => ({message:{related:[{doctype:'UA Invoice',name:'i/#',print_number:'<invoice>',docstatus:1,period_from:'2026-10-01',period_to:'2026-10-31'}]}})
    await t.refresh()
    const html = t.frm.dashboard.add_section.mock.calls.map(args => args[0]).join('')
    expect(html).toContain('/app/ua-invoice/i%2F%23')
    expect(html).toContain('&lt;invoice>')
    expect(html).not.toContain('><invoice>')
    expect(html).toContain('/crm/organizations/company%20%2F1?tab=documents')
  })
})
