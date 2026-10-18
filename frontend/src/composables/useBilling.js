import { createResource } from 'frappe-ui'
import { onMounted, ref, watch } from 'vue'

const capabilities = createResource({ url: 'crm.api.billing.get_capabilities' })

export function useBilling() {
  onMounted(() => {
    if (!capabilities.data && !capabilities.loading) capabilities.fetch()
  })
  return capabilities
}

export function useBillingDocumentTab(billing, route, fallback) {
  const activeTab = ref(fallback)
  watch(
    [
      () => route.query.tab,
      () => billing.data?.enabled,
      () => billing.data?.can_read,
    ],
    ([tab, enabled, canRead]) => {
      if (tab === 'documents' && enabled && canRead)
        activeTab.value = 'documents'
    },
    { immediate: true },
  )
  return activeTab
}
