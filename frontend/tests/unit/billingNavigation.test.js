import { afterEach, describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

const scriptPath = path.resolve(
  import.meta.dirname,
  '../../../extensions/recuite_billing/recuite_billing/public/js/navigation.js',
)
const source = existsSync(scriptPath) ? readFileSync(scriptPath, 'utf8') : ''

function loadNavigation() {
  let onReady
  new Function('$', source)(() => ({
    on: (event, handler) => {
      expect(event).toBe('app_ready')
      onReady = handler
    },
  }))
  return () => onReady?.()
}

afterEach(() => {
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

  it('does not break pages without the Desk toolbar', () => {
    document.body.innerHTML = '<main>Page without a toolbar</main>'
    expect(() => loadNavigation()()).not.toThrow()
    expect(document.querySelector('a')).toBeNull()
  })
})
