<script setup lang="ts">
import { computed } from 'vue'
import type { ReminderKind } from '../api'
import { errorText, input, label } from '../ui'

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

const snoozeText = computed({
  get: () => props.snoozeMinutes.join(', '),
  set: (val: string) => {
    const parsed = val
      .split(',')
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !Number.isNaN(n))
      .slice(0, 3)
    emit('update:snoozeMinutes', parsed)
  },
})

const clearableWarning = computed(
  () => !props.dismissible && props.snoozeMinutes.length === 0,
)
</script>

<template>
  <div class="flex gap-3 flex-wrap">
    <div>
      <label :class="label">Kind</label>
      <select
        :value="kind"
        :class="input"
        @change="emit('update:kind', ($event.target as HTMLSelectElement).value as ReminderKind)"
      >
        <option value="generic">Generic</option>
        <option value="medication">Medication</option>
        <option value="appointment">Appointment</option>
      </select>
    </div>

    <div>
      <label :class="label">
        <input
          type="checkbox"
          :checked="dismissible"
          class="w-auto inline-block mr-1.5 align-middle"
          @change="emit('update:dismissible', ($event.target as HTMLInputElement).checked)"
        />
        Dismissible on watch
      </label>
    </div>

    <div>
      <label :class="label">Snooze minutes (up to 3, comma separated)</label>
      <input v-model="snoozeText" placeholder="5, 15" :class="input" />
    </div>
  </div>
  <p v-if="clearableWarning" :class="[errorText, 'mt-2']">
    Not dismissible and no snooze options: this reminder could never be cleared on the watch.
  </p>
</template>
