<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ReminderKind } from '../api'
import { KINDS, KIND_ORDER } from '../kinds'
import AppIcon from './AppIcon.vue'
import MinutesPicker from './MinutesPicker.vue'
import ToggleSwitch from './ToggleSwitch.vue'

const props = defineProps<{
  kind: ReminderKind
  dismissible: boolean
  snoozeMinutes: number[]
}>()

const emit = defineEmits<{
  'update:kind': [ReminderKind]
  'update:dismissible': [boolean]
  'update:snoozeMinutes': [number[]]
}>()

const SNOOZE_PRESETS = [5, 10, 15, 30, 60]

const stuck = computed(() => !props.dismissible && props.snoozeMinutes.length === 0)

/** Watch behaviour is a "set once, forget" thing: tucked away unless it needs attention. */
const showWatch = ref(stuck.value)

const watchSummary = computed(() => {
  const parts = [props.dismissible ? 'Can be dismissed' : 'Must be snoozed or done']
  if (props.snoozeMinutes.length) parts.push(`snooze ${props.snoozeMinutes.join(' / ')} min`)
  return parts.join(' · ')
})
</script>

<template>
  <div class="space-y-5">
    <div>
      <span id="kind-label" class="field-label">Type</span>
      <div class="flex flex-wrap gap-2" role="radiogroup" aria-labelledby="kind-label">
        <button
          v-for="k in KIND_ORDER"
          :key="k"
          type="button"
          role="radio"
          :aria-checked="kind === k"
          class="chip"
          :class="{ 'chip-on': kind === k }"
          @click="emit('update:kind', k)"
        >
          <AppIcon :name="KINDS[k].icon" :size="18" />
          {{ KINDS[k].label }}
        </button>
      </div>
    </div>

    <div class="rounded-2xl border-2 border-stone-200 dark:border-stone-800">
      <button
        type="button"
        class="w-full flex items-center justify-between gap-3 px-4 py-3 text-left"
        :aria-expanded="showWatch"
        @click="showWatch = !showWatch"
      >
        <span>
          <span class="font-semibold block">On the watch</span>
          <span class="text-sm muted">{{ watchSummary }}</span>
        </span>
        <AppIcon name="chevron-down" class="transition-transform" :class="{ 'rotate-180': showWatch }" />
      </button>
      <div v-if="showWatch" class="px-4 pb-4 space-y-4">
        <ToggleSwitch
          :model-value="dismissible"
          label="Allow dismissing it"
          @update:model-value="(v: boolean) => emit('update:dismissible', v)"
        />
        <div>
          <span id="snooze-label" class="field-label">Snooze options <span class="font-normal muted">(up to 3)</span></span>
          <MinutesPicker
            labelledby="snooze-label"
            :model-value="snoozeMinutes"
            :presets="SNOOZE_PRESETS"
            :max="3"
            @update:model-value="(v: number[]) => emit('update:snoozeMinutes', v)"
          />
        </div>
      </div>
    </div>

    <p v-if="stuck" class="error-box text-sm" role="alert">
      This reminder could never be cleared on the watch. Turn on dismissing, or pick at least one snooze option.
    </p>
  </div>
</template>
