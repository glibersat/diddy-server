<script setup lang="ts" generic="T extends string">
defineProps<{ modelValue: T; options: { value: T; label: string }[]; label: string }>()
const emit = defineEmits<{ 'update:modelValue': [T] }>()
</script>

<template>
  <div role="radiogroup" :aria-label="label" class="inline-flex rounded-xl bg-stone-100 dark:bg-stone-800 p-1 gap-1">
    <button
      v-for="o in options"
      :key="o.value"
      type="button"
      role="radio"
      :aria-checked="modelValue === o.value"
      class="min-h-9 rounded-lg px-3.5 text-sm font-semibold transition-colors"
      :class="
        modelValue === o.value
          ? 'bg-white text-stone-900 shadow-sm dark:bg-stone-950 dark:text-stone-100'
          : 'text-stone-600 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100'
      "
      @click="emit('update:modelValue', o.value)"
    >
      {{ o.label }}
    </button>
  </div>
</template>
