<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'

/**
 * A focused editing panel: slides up from the bottom on phones, from the right on desktop.
 * The page behind is dimmed so there's only one thing to look at. Esc / backdrop closes it.
 */
const props = defineProps<{ open: boolean; title: string }>()
const emit = defineEmits<{ close: [] }>()

const panel = ref<HTMLElement | null>(null)

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}

watch(
  () => props.open,
  async (open) => {
    if (open) {
      document.addEventListener('keydown', onKey)
      document.body.style.overflow = 'hidden'
      await nextTick()
      const first = panel.value?.querySelector<HTMLElement>('[autofocus], input, select, textarea')
      first?.focus()
    } else {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  },
)

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  document.body.style.overflow = ''
})
</script>

<template>
  <Teleport to="body">
    <Transition
      enter-from-class="opacity-0"
      leave-to-class="opacity-0"
      enter-active-class="transition-opacity duration-200"
      leave-active-class="transition-opacity duration-150"
    >
      <div v-if="open" class="fixed inset-0 z-40 bg-stone-950/40 backdrop-blur-[2px]" @click="emit('close')" />
    </Transition>
    <Transition
      enter-from-class="translate-y-full md:translate-y-0 md:translate-x-full"
      leave-to-class="translate-y-full md:translate-y-0 md:translate-x-full"
      enter-active-class="transition-transform duration-200 ease-out"
      leave-active-class="transition-transform duration-150 ease-in"
    >
      <section
        v-if="open"
        ref="panel"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        class="fixed z-50 inset-x-0 bottom-0 max-h-[92vh] rounded-t-3xl md:inset-y-0 md:left-auto md:right-0 md:max-h-none md:w-[32rem] md:rounded-none md:rounded-l-3xl bg-white dark:bg-stone-900 shadow-2xl flex flex-col"
      >
        <header class="flex items-center justify-between gap-3 px-6 pt-5 pb-3">
          <h2 class="text-xl font-bold">{{ title }}</h2>
          <button type="button" class="btn btn-ghost !px-2.5" aria-label="Close" @click="emit('close')">
            <AppIcon name="x" :size="22" />
          </button>
        </header>
        <div class="overflow-y-auto px-6 pb-6 flex-1">
          <slot />
        </div>
      </section>
    </Transition>
  </Teleport>
</template>
