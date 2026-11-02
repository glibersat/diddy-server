<script setup lang="ts">
import AppIcon from '../components/AppIcon.vue'
import PageHeader from '../components/PageHeader.vue'
import { SECONDARY_NAV } from '../nav'
</script>

<template>
  <div>
    <PageHeader title="More" />
    <ul class="space-y-2">
      <li v-for="n in SECONDARY_NAV" :key="n.to">
        <RouterLink :to="n.to" class="card flex items-center gap-4 hover:border-indigo-300 dark:hover:border-indigo-700">
          <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300">
            <AppIcon :name="n.icon" :size="22" />
          </span>
          <span class="flex-1">
            <span class="block font-semibold">{{ n.label }}</span>
            <span class="text-sm muted">{{ n.hint }}</span>
          </span>
          <AppIcon name="chevron-right" class="muted" />
        </RouterLink>
      </li>
    </ul>
  </div>
</template>
