<template>
  <section class="space-y-4 p-4" aria-label="Документи компанії">
    <a
      :href="documentURL('CRM Organization', props.organization)"
      class="inline-block text-sm underline"
      >Реквізити компанії →</a
    >
    <div class="flex flex-wrap gap-2">
      <Button
        v-for="item in kinds"
        :key="item.value"
        :variant="kind === item.value ? 'solid' : 'subtle'"
        @click="select(item.value)"
        >{{ item.label }}</Button
      >
      <a
        v-if="capabilities.data?.create?.[doctype]"
        :href="newDocumentURL"
        class="ml-auto rounded border px-3 py-1.5 text-sm"
        >Створити</a
      >
      <Button :loading="documents.loading" @click="documents.fetch()"
        >Оновити</Button
      >
    </div>
    <ErrorMessage v-if="documents.error" :message="documents.error" />
    <p v-else-if="documents.loading">Завантаження…</p>
    <p
      v-else-if="!documents.data?.rows?.length"
      class="py-8 text-center text-ink-gray-5"
    >
      Документів поки немає
    </p>
    <ul v-else class="divide-y rounded-lg border">
      <li
        v-for="row in documents.data.rows"
        :key="row.name"
        class="flex flex-wrap items-center justify-between gap-2 p-3"
      >
        <a :href="documentURL(doctype, row.name)" class="min-w-0 flex-1">
          <div class="break-words font-medium">
            {{ row.print_number || row.contract_number || row.name }}
          </div>
          <div class="text-sm text-ink-gray-5">
            {{ row.issuer }} ·
            {{
              kind === 'contracts'
                ? row.contract_date
                : documentStatus(row.docstatus)
            }}
          </div>
          <div v-if="row.period_from" class="text-sm text-ink-gray-5">
            {{ row.period_from }} — {{ row.period_to }}
          </div>
        </a>
        <span v-if="kind !== 'contracts'" class="text-sm"
          >{{ amount(row.grand_total) }} грн</span
        >
        <a
          v-if="rowAction(row)"
          :href="actionURL(row)"
          class="rounded border px-3 py-1.5 text-sm hover:bg-surface-gray-1 focus-visible:outline focus-visible:outline-2"
          :aria-label="`${rowAction(row).label}: ${row.print_number || row.contract_number || row.name}`"
          >{{ rowAction(row).label }}</a
        >
        <a
          v-if="row.pdf_file"
          :href="pdfURL(row.name)"
          class="rounded border px-3 py-1.5 text-sm"
          :aria-label="`PDF ${row.print_number || row.name}`"
          >PDF</a
        >
      </li>
    </ul>
    <div class="flex items-center gap-3">
      <Button :disabled="start === 0 || documents.loading" @click="page(-1)"
        >Назад</Button
      >
      <span class="text-sm">{{ Math.floor(start / 20) + 1 }}</span>
      <Button
        :disabled="!documents.data?.has_more || documents.loading"
        @click="page(1)"
        >Далі</Button
      >
    </div>
  </section>
</template>
<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button, ErrorMessage, createResource } from 'frappe-ui'
import { useBilling } from '@/composables/useBilling'
import { documentURL, documentStatus, documentAction } from '@/utils/billing'
const props = defineProps({ organization: { type: String, required: true } })
const kinds = [
  { value: 'contracts', label: 'Договори', doctype: 'UA Contract' },
  { value: 'invoices', label: 'Рахунки', doctype: 'UA Invoice' },
  { value: 'acts', label: 'Акти', doctype: 'UA Act' },
]
const route = useRoute()
const router = useRouter()
const kind = ref(
  kinds.some((item) => item.value === route.query.kind)
    ? route.query.kind
    : 'contracts',
)
const initialStart = Number(route.query.document_start)
const start = ref(
  Number.isFinite(initialStart)
    ? Math.max(0, Math.floor(initialStart / 20) * 20)
    : 0,
)
const capabilities = useBilling()
const doctype = computed(
  () => kinds.find((item) => item.value === kind.value).doctype,
)
const documents = createResource({
  url: 'recuite_billing.api.get_organization_documents',
  makeParams: () => ({
    organization: props.organization,
    kind: kind.value,
    start: start.value,
    page_length: 20,
  }),
})
watch([() => props.organization, kind, start], () => documents.fetch(), {
  immediate: true,
})
const newDocumentURL = computed(
  () =>
    `${documentURL(doctype.value, `new-${doctype.value.toLowerCase().replaceAll(' ', '-')}`)}?organization=${encodeURIComponent(props.organization)}`,
)
const amount = (value) =>
  new Intl.NumberFormat('uk-UA', { minimumFractionDigits: 2 }).format(
    value || 0,
  )
const pdfURL = (name) =>
  `/api/method/recuite_billing.printing.download_pdf?doctype=${encodeURIComponent(doctype.value)}&name=${encodeURIComponent(name)}`
const rowAction = (row) => documentAction(kind.value, row, capabilities.data)
function actionURL(row) {
  const action = rowAction(row)?.action
  return (
    documentURL(doctype.value, row.name) +
    (action ? `?billing_action=${action}` : '')
  )
}
function remember() {
  router.replace({
    query: {
      ...route.query,
      tab: 'documents',
      kind: kind.value,
      document_start: start.value || undefined,
    },
  })
}
function select(value) {
  start.value = 0
  kind.value = value
  remember()
}
function page(direction) {
  start.value += direction * 20
  remember()
}
</script>
