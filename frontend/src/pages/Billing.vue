<template>
  <div class="flex h-full flex-col overflow-auto">
    <header class="border-b px-5 py-4">
      <h1 class="text-xl font-semibold">Документи</h1>
    </header>
    <div class="mx-auto w-full max-w-4xl space-y-6 p-5">
      <p class="text-ink-gray-6">
        Договори, рахунки й акти у гривні. Для створення та редагування
        відкриється форма документа.
      </p>
      <ErrorMessage v-if="capabilities.error" :message="capabilities.error" />
      <p v-else-if="capabilities.loading">Завантаження…</p>
      <p v-else-if="!links.length">
        Розділ недоступний. Потрібні встановлений модуль документів та
        відповідна роль.
      </p>
      <div v-else class="grid gap-3 sm:grid-cols-2">
        <a
          v-for="link in links"
          :key="link.doctype"
          :href="link.href"
          class="rounded-lg border bg-surface-white p-5 text-lg font-medium hover:bg-surface-gray-1 focus-visible:outline focus-visible:outline-2"
        >
          {{ link.label }} <span aria-hidden="true">→</span>
        </a>
      </div>
      <p class="text-sm text-ink-gray-6">
        Почніть з реквізитів виконавця, компанії-замовника та каталогу. У
        договорі оберіть періодичність рахунків і актів. Скан підпису та печатки
        вмикається окремо перед випуском кожного документа.
      </p>
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
import { ErrorMessage } from 'frappe-ui'
import { useBilling } from '@/composables/useBilling'
import { billingLinks } from '@/utils/billing'
const capabilities = useBilling()
const links = computed(() => billingLinks(capabilities.data))
</script>
