<script setup lang="ts">
import { computed } from 'vue'

/**
 * Pick a few minute values by tapping chips instead of typing a comma-separated list.
 * Values already in `modelValue` that aren't presets still show (so nothing is silently lost).
 */
const props = withDefaults(
  defineProps<{ modelValue: number[]; presets: number[]; max?: number; labelledby?: string }>(),
  { max: Infinity },
)
const emit = defineEmits<{ 'update:modelValue': [number[]] }>()

const options = computed(() => [...new Set([...props.presets, ...props.modelValue])].sort((a, b) => a - b))
const full = computed(() => props.modelValue.length >= props.max)

function fmt(m: number): string {
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  const rest = m % 60
  return rest ? `${h} h ${rest}` : `${h} h`
}

function toggle(m: number) {
  if (props.modelValue.includes(m)) {
    emit('update:modelValue', props.modelValue.filter((v) => v !== m))
  } else if (!full.value) {
    emit('update:modelValue', [...props.modelValue, m].sort((a, b) => b - a))
  }
}
</script>

<template>
  <div class="flex flex-wrap gap-2" role="group" :aria-labelledby="labelledby">
    <button
      v-for="m in options"
      :key="m"
      type="button"
      class="chip"
      :class="{ 'chip-on': modelValue.includes(m), 'opacity-40': full && !modelValue.includes(m) }"
      :aria-pressed="modelValue.includes(m)"
      :disabled="full && !modelValue.includes(m)"
      @click="toggle(m)"
    >
      {{ fmt(m) }}
    </button>
  </div>
</template>
