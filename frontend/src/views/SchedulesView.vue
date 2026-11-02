<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  createSchedule,
  deleteSchedule,
  listSchedules,
  updateSchedule,
  type DailySchedule,
  type DailyScheduleInput,
  type ReminderKind,
} from '../api'
import AppIcon from '../components/AppIcon.vue'
import DeleteButton from '../components/DeleteButton.vue'
import EditSheet from '../components/EditSheet.vue'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import ReminderOptions from '../components/ReminderOptions.vue'
import ToggleSwitch from '../components/ToggleSwitch.vue'
import { KINDS } from '../kinds'
import { shortTime } from '../time'
import { WEEKDAYS, describeMask, maskHasDay, toggleDay } from '../weekdays'

const schedules = ref<DailySchedule[]>([])
const loading = ref(true)
const error = ref('')
const formError = ref('')
const sheetOpen = ref(false)
const saving = ref(false)

const DAY_PRESETS = [
  { label: 'Every day', mask: 0b1111111 },
  { label: 'Weekdays', mask: 0b0011111 },
  { label: 'Weekends', mask: 0b1100000 },
]

function blankForm(): DailyScheduleInput {
  return {
    time_of_day: '09:00',
    weekdays_mask: 0b1111111,
    message: '',
    enabled: true,
    kind: 'medication',
    dismissible: false,
    snooze_minutes: [5, 15],
  }
}

const form = reactive<DailyScheduleInput>(blankForm())
const editingId = ref<string | null>(null)

async function refresh() {
  error.value = ''
  try {
    schedules.value = await listSchedules()
  } catch (e) {
    error.value = "Couldn't load your routines. Try again in a moment."
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

/** Morning / afternoon / evening buckets: easier to scan than one long list. */
const groups = computed(() => {
  const sorted = [...schedules.value].sort((a, b) => a.time_of_day.localeCompare(b.time_of_day))
  const buckets = [
    { label: 'Morning', items: sorted.filter((s) => s.time_of_day < '12:00') },
    { label: 'Afternoon', items: sorted.filter((s) => s.time_of_day >= '12:00' && s.time_of_day < '18:00') },
    { label: 'Evening', items: sorted.filter((s) => s.time_of_day >= '18:00') },
  ]
  return buckets.filter((b) => b.items.length)
})

function openCreate() {
  Object.assign(form, blankForm())
  editingId.value = null
  formError.value = ''
  sheetOpen.value = true
}

function openEdit(s: DailySchedule) {
  Object.assign(form, {
    time_of_day: shortTime(s.time_of_day),
    weekdays_mask: s.weekdays_mask,
    message: s.message,
    enabled: s.enabled,
    kind: s.kind,
    dismissible: s.dismissible,
    snooze_minutes: [...s.snooze_minutes],
  })
  editingId.value = s.id
  formError.value = ''
  sheetOpen.value = true
}

async function submit() {
  if (!form.dismissible && form.snooze_minutes.length === 0) {
    formError.value = 'Pick a snooze option or allow dismissing, otherwise it could never be cleared.'
    return
  }
  if (form.weekdays_mask === 0) {
    formError.value = 'Pick at least one day.'
    return
  }
  saving.value = true
  formError.value = ''
  try {
    if (editingId.value) await updateSchedule(editingId.value, form)
    else await createSchedule(form)
    sheetOpen.value = false
    await refresh()
  } catch (e: any) {
    formError.value = e?.response?.data?.detail ?? "Couldn't save. Try again."
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!editingId.value) return
  try {
    await deleteSchedule(editingId.value)
    sheetOpen.value = false
    await refresh()
  } catch {
    formError.value = "Couldn't delete. Try again."
  }
}

/** Optimistic: flip it right away, roll back if the server says no. */
async function setEnabled(s: DailySchedule, enabled: boolean) {
  s.enabled = enabled
  try {
    await updateSchedule(s.id, { enabled })
  } catch {
    s.enabled = !enabled
    error.value = "Couldn't change that routine. Try again."
  }
}
</script>

<template>
  <div>
    <PageHeader title="Routines" subtitle="Reminders that come back at the same time, like taking your meds.">
      <button v-if="schedules.length" class="btn btn-primary" @click="openCreate">
        <AppIcon name="plus" /> New routine
      </button>
    </PageHeader>

    <p v-if="error" class="error-box mb-4" role="alert">{{ error }}</p>

    <div v-if="loading" class="space-y-3" aria-busy="true">
      <div v-for="i in 3" :key="i" class="card h-20 animate-pulse" />
    </div>

    <EmptyState
      v-else-if="!schedules.length"
      icon="repeat"
      title="No routines yet"
      text="Add one thing you want to remember every day. You can always change it later."
    >
      <button class="btn btn-primary" @click="openCreate"><AppIcon name="plus" /> Add your first routine</button>
    </EmptyState>

    <div v-else class="space-y-6">
      <section v-for="g in groups" :key="g.label">
        <h2 class="text-sm font-bold uppercase tracking-wider muted mb-2">{{ g.label }}</h2>
        <ul class="space-y-2">
          <li
            v-for="s in g.items"
            :key="s.id"
            class="card !p-0 flex items-stretch overflow-hidden transition-opacity"
            :class="{ 'opacity-55': !s.enabled }"
          >
            <span class="w-1.5 shrink-0" :class="s.enabled ? KINDS[s.kind].stripe : 'bg-stone-300 dark:bg-stone-700'" aria-hidden="true" />
            <button
              type="button"
              class="flex flex-1 items-center gap-4 px-4 py-3.5 text-left min-w-0 hover:bg-stone-50 dark:hover:bg-stone-800/50"
              :aria-label="`Edit ${s.message}`"
              @click="openEdit(s)"
            >
              <span class="tabular-nums text-xl font-bold w-16 shrink-0">{{ shortTime(s.time_of_day) }}</span>
              <span class="min-w-0 flex-1">
                <span class="block font-semibold break-words">{{ s.message }}</span>
                <span class="text-sm muted inline-flex items-center gap-1.5 flex-wrap">
                  <AppIcon :name="KINDS[s.kind].icon" :size="14" />
                  {{ KINDS[s.kind].label }} · {{ describeMask(s.weekdays_mask) }}
                </span>
              </span>
              <AppIcon name="pencil" :size="18" class="muted shrink-0 hidden sm:block" />
            </button>
            <div class="flex items-center pr-4 pl-1">
              <ToggleSwitch
                :model-value="s.enabled"
                :label="s.enabled ? `Turn off ${s.message}` : `Turn on ${s.message}`"
                hide-label
                @update:model-value="(v: boolean) => setEnabled(s, v)"
              />
            </div>
          </li>
        </ul>
      </section>
    </div>

    <EditSheet :open="sheetOpen" :title="editingId ? 'Edit routine' : 'New routine'" @close="sheetOpen = false">
      <form class="space-y-6" @submit.prevent="submit">
        <div>
          <label for="message" class="field-label">What should it say?</label>
          <input id="message" v-model="form.message" required autofocus placeholder="Take your meds" class="field text-lg" />
        </div>

        <div>
          <label for="time" class="field-label">At what time?</label>
          <input id="time" v-model="form.time_of_day" type="time" required class="field !w-auto text-lg tabular-nums" />
        </div>

        <div>
          <span id="days-label" class="field-label">On which days?</span>
          <div class="flex flex-wrap gap-2 mb-2">
            <button
              v-for="p in DAY_PRESETS"
              :key="p.label"
              type="button"
              class="chip"
              :class="{ 'chip-on': form.weekdays_mask === p.mask }"
              @click="form.weekdays_mask = p.mask"
            >
              {{ p.label }}
            </button>
          </div>
          <div class="flex flex-wrap gap-1.5" role="group" aria-labelledby="days-label">
            <button
              v-for="d in WEEKDAYS"
              :key="d.bit"
              type="button"
              class="h-11 w-11 rounded-full font-semibold border-2 transition-colors"
              :class="
                maskHasDay(form.weekdays_mask, d.bit)
                  ? 'border-indigo-600 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-950 dark:text-indigo-200'
                  : 'border-stone-200 text-stone-500 dark:border-stone-700 dark:text-stone-400'
              "
              :aria-pressed="maskHasDay(form.weekdays_mask, d.bit)"
              :aria-label="d.label"
              @click="form.weekdays_mask = toggleDay(form.weekdays_mask, d.bit)"
            >
              {{ d.label.slice(0, 2) }}
            </button>
          </div>
        </div>

        <ReminderOptions
          :kind="form.kind"
          :dismissible="form.dismissible"
          :snooze-minutes="form.snooze_minutes"
          @update:kind="(v: ReminderKind) => (form.kind = v)"
          @update:dismissible="(v: boolean) => (form.dismissible = v)"
          @update:snooze-minutes="(v: number[]) => (form.snooze_minutes = v)"
        />

        <p v-if="formError" class="error-box" role="alert">{{ formError }}</p>

        <div class="flex flex-wrap items-center gap-3 pt-2">
          <button type="submit" :disabled="saving" class="btn btn-primary flex-1 sm:flex-none">
            {{ saving ? 'Saving…' : editingId ? 'Save changes' : 'Add routine' }}
          </button>
          <button type="button" class="btn btn-ghost" @click="sheetOpen = false">Cancel</button>
          <DeleteButton v-if="editingId" class="sm:ml-auto" @confirm="remove" />
        </div>
      </form>
    </EditSheet>
  </div>
</template>
