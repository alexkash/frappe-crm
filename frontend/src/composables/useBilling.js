import { createResource } from 'frappe-ui'
import { onMounted } from 'vue'

const capabilities = createResource({ url: 'crm.api.billing.get_capabilities' })

export function useBilling() {
  onMounted(() => {
    if (!capabilities.data && !capabilities.loading) capabilities.fetch()
  })
  return capabilities
}
