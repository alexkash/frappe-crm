import { afterEach, describe, expect, it, vi } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

const scriptPath = path.resolve(
  import.meta.dirname,
  '../../../extensions/recuite_billing/recuite_billing/public/js/navigation.js',
)
const source = existsSync(scriptPath) ? readFileSync(scriptPath, 'utf8') : ''

function loadNavigation(frappe = {}) {
  let onReady
  new Function('$', 'frappe', source)(
    () => ({
      on: (event, handler) => {
        expect(event).toBe('app_ready')
        onReady = handler
      },
    }),
    frappe,
  )
  return () => onReady?.()
}

afterEach(() => {
  vi.restoreAllMocks()
  delete window.cur_frm
  document.body.innerHTML = ''
})

describe('billing return navigation', () => {
  it('offers one real CRM link on lists and forms after Desk starts', () => {
    document.body.innerHTML =
      '<header class="navbar"><a class="navbar-home" href="/app">Frappe</a><ul id="navbar-breadcrumbs"></ul></header>'
    const ready = loadNavigation()
    ready()
    const link = document.querySelector('a[href="/crm/billing"]')
    expect(link).not.toBeNull()
    expect(link.textContent).toContain('CRM')
    expect(link.getAttribute('aria-label')).toBeTruthy()
    expect(document.querySelector('.navbar-home').nextElementSibling).toBe(link)
    expect(link.hasAttribute('target')).toBe(false)
    ready()
    expect(document.querySelectorAll('a[href="/crm/billing"]')).toHaveLength(1)
  })

  it('confirms before discarding an unsaved form and keeps modified clicks native', () => {
    document.body.innerHTML = '<a class="navbar-home" href="/app">Frappe</a>'
    const confirm = vi.fn()
    const navigate = vi
      .spyOn(window.location, 'assign')
      .mockImplementation(() => {})
    window.cur_frm = { is_dirty: () => true, beforeUnloadListener: () => {} }
    loadNavigation({ get_route: () => ['Form', 'UA Contract'], confirm })()
    const link = document.querySelector('a[href="/crm/billing"]')
    const click = new MouseEvent('click', { bubbles: true, cancelable: true })
    link.dispatchEvent(click)
    expect(click.defaultPrevented).toBe(true)
    expect(confirm).toHaveBeenCalledOnce()
    expect(navigate).not.toHaveBeenCalled()
    confirm.mock.calls[0][1]()
    expect(navigate).toHaveBeenCalledWith(link.href)
    const modified = new MouseEvent('click', {
      cancelable: true,
      ctrlKey: true,
    })
    link.dispatchEvent(modified)
    expect(modified.defaultPrevented).toBe(false)
    expect(confirm).toHaveBeenCalledOnce()
  })

  it('does not break pages without the Desk toolbar', () => {
    document.body.innerHTML = '<main>Page without a toolbar</main>'
    expect(() => loadNavigation()()).not.toThrow()
    expect(document.querySelector('a')).toBeNull()
  })
})
