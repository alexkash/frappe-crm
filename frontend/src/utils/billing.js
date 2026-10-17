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
