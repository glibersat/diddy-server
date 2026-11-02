<script setup lang="ts">
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <header class="mb-6 flex items-start justify-between gap-4 flex-wrap">
    <div class="min-w-0">
      <h1 class="text-2xl md:text-3xl font-bold tracking-tight">{{ title }}</h1>
      <p v-if="subtitle" class="muted mt-1 max-w-prose">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.default" class="flex items-center gap-2 flex-wrap">
      <slot />
    </div>
  </header>
</template>
