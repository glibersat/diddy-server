<script setup lang="ts">
defineProps<{ modelValue: boolean; label: string; hideLabel?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()
</script>

<template>
  <button
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :aria-label="hideLabel ? label : undefined"
    class="inline-flex items-center gap-3 min-h-11 text-left"
    @click="emit('update:modelValue', !modelValue)"
  >
    <span
      class="relative inline-block h-7 w-12 shrink-0 rounded-full transition-colors"
      :class="modelValue ? 'bg-indigo-600' : 'bg-stone-300 dark:bg-stone-700'"
    >
      <span
        class="absolute top-1 left-1 h-5 w-5 rounded-full bg-white shadow transition-transform"
        :class="modelValue ? 'translate-x-5' : 'translate-x-0'"
      />
    </span>
    <span v-if="!hideLabel" class="font-medium">{{ label }}</span>
  </button>
</template>
