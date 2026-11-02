<script setup lang="ts">
import AppIcon from './AppIcon.vue'
import type { IconName } from '../icons'

defineProps<{ icon: IconName; title: string; text?: string }>()
</script>

<template>
  <div class="card border-dashed text-center py-10 px-6">
    <div class="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300">
      <AppIcon :name="icon" :size="28" />
    </div>
    <p class="text-lg font-semibold">{{ title }}</p>
    <p v-if="text" class="muted mt-1 max-w-sm mx-auto">{{ text }}</p>
    <div v-if="$slots.default" class="mt-5">
      <slot />
    </div>
  </div>
</template>
