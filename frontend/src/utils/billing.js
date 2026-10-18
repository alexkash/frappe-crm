export function billingLinks(capabilities) {
  if (!capabilities?.enabled || !capabilities.can_read) return []
  return [
    ['UA Contract', 'Договори'],
    ['UA Invoice', 'Рахунки'],
    ['UA Act', 'Акти'],
    ['CRM Product', 'Каталог продуктів і послуг'],
    ...(capabilities.can_manage
      ? [
          ['UA Issuer', 'Наші виконавці'],
          ['UA Print Asset', 'Логотипи, підписи та печатки'],
        ]
      : []),
  ].map(([doctype, label]) => ({
    doctype,
    label,
    href: `/app/${doctype.toLowerCase().replaceAll(' ', '-')}`,
    canCreate: !!capabilities.can_create,
  }))
}

export function documentURL(doctype, name) {
  return `/app/${doctype.toLowerCase().replaceAll(' ', '-')}/${encodeURIComponent(name)}`
}

export function documentStatus(status) {
  return ['Чернетка', 'Випущено', 'Скасовано'][status] || ''
}


export function documentAction(kind, row, capabilities) {
  if (kind === 'contracts' && !row.disabled && capabilities?.create?.['UA Invoice'])
    return { label: 'Створити рахунок', action: 'invoice' }
  if (kind === 'invoices' && row.docstatus === 0)
    return { label: 'Продовжити оформлення', action: null }
  if (kind === 'invoices' && row.docstatus === 1 && capabilities?.create?.['UA Act'])
    return { label: 'Створити акт', action: 'act' }
  return null
}
