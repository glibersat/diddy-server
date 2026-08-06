<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  createSchedule,
  deleteSchedule,
  listSchedules,
  updateSchedule,
  type DailySchedule,
  type DailyScheduleInput,
  type ReminderKind,
} from '../api'
import ReminderOptions from '../components/ReminderOptions.vue'
import { WEEKDAYS, describeMask, maskHasDay, toggleDay } from '../weekdays'
import { btnDanger, btnPrimary, btnSecondary, card, errorText, input, label, muted } from '../ui'

const schedules = ref<DailySchedule[]>([])
const loading = ref(true)
const error = ref('')
const showForm = ref(false)
const saving = ref(false)

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
  loading.value = true
  error.value = ''
  try {
    schedules.value = await listSchedules()
  } catch (e) {
    error.value = 'Could not load daily reminders'
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

function startCreate() {
  Object.assign(form, blankForm())
  editingId.value = null
  showForm.value = true
}

function startEdit(s: DailySchedule) {
  Object.assign(form, {
    time_of_day: s.time_of_day,
    weekdays_mask: s.weekdays_mask,
    message: s.message,
    enabled: s.enabled,
    kind: s.kind,
    dismissible: s.dismissible,
    snooze_minutes: [...s.snooze_minutes],
  })
  editingId.value = s.id
  showForm.value = true
}

function cancelForm() {
  showForm.value = false
  editingId.value = null
}

async function submitForm() {
  if (!form.dismissible && form.snooze_minutes.length === 0) {
    error.value = 'Add a snooze option or make the reminder dismissible'
    return
  }
  saving.value = true
  error.value = ''
  try {
    if (editingId.value) {
      await updateSchedule(editingId.value, form)
    } else {
      await createSchedule(form)
    }
    showForm.value = false
    await refresh()
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? 'Could not save reminder'
  } finally {
    saving.value = false
  }
}

async function remove(s: DailySchedule) {
  if (!confirm(`Delete reminder "${s.message}"?`)) return
  await deleteSchedule(s.id)
  await refresh()
}

async function toggleEnabled(s: DailySchedule) {
  await updateSchedule(s.id, { enabled: !s.enabled })
  await refresh()
}

function onToggleDay(bit: number) {
  form.weekdays_mask = toggleDay(form.weekdays_mask, bit)
}
</script>

<template>
  <div>
    <div class="flex justify-between items-center">
      <h2 class="text-base font-semibold">Daily Reminders</h2>
      <button v-if="!showForm" :class="btnPrimary" @click="startCreate">+ New reminder</button>
    </div>
    <p :class="[muted, 'mb-4']">Fires at a fixed local time on the days you choose, e.g. "take your meds".</p>

    <div v-if="showForm" :class="card">
      <h3 class="font-semibold mb-3">{{ editingId ? 'Edit reminder' : 'New reminder' }}</h3>
      <form class="space-y-4" @submit.prevent="submitForm">
        <div class="flex gap-3 flex-wrap">
          <div>
            <label for="time" :class="label">Time of day</label>
            <input id="time" v-model="form.time_of_day" type="time" required :class="input" />
          </div>
          <div class="flex-1 min-w-48">
            <label for="message" :class="label">Message</label>
            <input
              id="message"
              v-model="form.message"
              required
              placeholder="Take your meds"
              :class="[input, 'w-full']"
            />
          </div>
        </div>

        <div>
          <label :class="label">Days</label>
          <div class="flex gap-1.5 flex-wrap">
            <button
              v-for="d in WEEKDAYS"
              :key="d.bit"
              type="button"
              class="rounded-md px-3 py-1.5"
              :class="
                maskHasDay(form.weekdays_mask, d.bit)
                  ? 'bg-indigo-600 text-white'
                  : 'bg-transparent border border-neutral-300 dark:border-neutral-700 text-neutral-900 dark:text-neutral-100'
              "
              @click="onToggleDay(d.bit)"
            >
              {{ d.label }}
            </button>
          </div>
          <p :class="[muted, 'mt-1']">{{ describeMask(form.weekdays_mask) }}</p>
        </div>

        <ReminderOptions
          :kind="form.kind"
          :dismissible="form.dismissible"
          :snooze-minutes="form.snooze_minutes"
          @update:kind="(v: ReminderKind) => (form.kind = v)"
          @update:dismissible="(v: boolean) => (form.dismissible = v)"
          @update:snooze-minutes="(v: number[]) => (form.snooze_minutes = v)"
        />

        <div>
          <label :class="label">
            <input type="checkbox" v-model="form.enabled" class="w-auto inline-block mr-1.5 align-middle" />
            Enabled
          </label>
        </div>

        <p v-if="error" :class="errorText">{{ error }}</p>

        <div class="flex gap-3">
          <button type="submit" :disabled="saving" :class="btnPrimary">{{ saving ? 'Saving…' : 'Save' }}</button>
          <button type="button" :class="btnSecondary" @click="cancelForm">Cancel</button>
        </div>
      </form>
    </div>

    <p v-if="loading">Loading…</p>
    <p v-else-if="!schedules.length && !showForm" :class="muted">No daily reminders yet.</p>

    <div
      v-for="s in schedules"
      :key="s.id"
      :class="[card, 'flex justify-between items-center flex-wrap gap-3']"
    >
      <div class="flex items-center gap-4">
        <div class="tabular-nums text-lg font-semibold min-w-[4.5rem]">{{ s.time_of_day }}</div>
        <div>
          <div class="font-medium" :class="{ 'opacity-50 line-through': !s.enabled }">{{ s.message }}</div>
          <div :class="muted">
            {{ describeMask(s.weekdays_mask) }} · {{ s.kind }}
            <span v-if="s.dismissible">· dismissible</span>
            <span v-if="s.snooze_minutes.length">· snooze {{ s.snooze_minutes.join('/') }}m</span>
          </div>
        </div>
      </div>
      <div class="flex gap-3">
        <button :class="btnSecondary" @click="toggleEnabled(s)">{{ s.enabled ? 'Disable' : 'Enable' }}</button>
        <button :class="btnSecondary" @click="startEdit(s)">Edit</button>
        <button :class="btnDanger" @click="remove(s)">Delete</button>
      </div>
    </div>
  </div>
</template>
