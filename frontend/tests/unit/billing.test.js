import { describe, it, expect } from 'vitest'
import { billingLinks, documentStatus, documentURL } from '@/utils/billing'

describe('billing destinations', () => {
  it('offers no actions without billing access and no creation to readers', () => {
    expect(billingLinks({})).toEqual([])
    const links = billingLinks({ enabled: true, can_read: true })
    expect(links.map((link) => link.doctype)).toContain('CRM Product')
    expect(links.every((link) => !link.canCreate)).toBe(true)
    expect(
      billingLinks({ enabled: true, can_read: true, can_create: true }).find(
        (link) => link.doctype === 'UA Invoice',
      ).canCreate,
    ).toBe(true)
  })
  it('encodes names and reports cancelled documents without changing archives', () => {
    expect(documentURL('UA Invoice', 'test/# one')).toBe(
      '/app/ua-invoice/test%2F%23%20one',
    )
    expect(documentStatus(2)).toBe('Скасовано')
    expect(documentStatus(1)).toBe('Випущено')
    expect(documentStatus(0)).toBe('Чернетка')
  })
})
