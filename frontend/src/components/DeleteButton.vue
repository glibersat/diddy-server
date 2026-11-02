<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import AppIcon from './AppIcon.vue'

/**
 * Two-tap delete: the first tap asks "Sure?", the second one deletes. It resets by itself after
 * a few seconds, so a stray click never deletes anything and there's no blocking dialog.
 */
defineProps<{ label?: string }>()
const emit = defineEmits<{ confirm: [] }>()

const armed = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

function click() {
  if (armed.value) {
    clearTimeout(timer)
    armed.value = false
    emit('confirm')
    return
  }
  armed.value = true
  timer = setTimeout(() => (armed.value = false), 4000)
}

onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <button type="button" class="btn" :class="armed ? 'bg-red-600 text-white hover:bg-red-700' : 'btn-danger'" @click="click">
    <AppIcon name="trash" :size="18" />
    {{ armed ? 'Tap again to delete' : (label ?? 'Delete') }}
  </button>
</template>
