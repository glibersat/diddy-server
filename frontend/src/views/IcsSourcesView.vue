<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  createIcsSource,
  deleteIcsSource,
  listIcsSources,
  updateIcsSource,
  type IcsSource,
  type IcsSourceInput,
  type ReminderKind,
} from '../api'
import AppIcon from '../components/AppIcon.vue'
import DeleteButton from '../components/DeleteButton.vue'
import EditSheet from '../components/EditSheet.vue'
import EmptyState from '../components/EmptyState.vue'
import MinutesPicker from '../components/MinutesPicker.vue'
import PageHeader from '../components/PageHeader.vue'
import ReminderOptions from '../components/ReminderOptions.vue'
import ToggleSwitch from '../components/ToggleSwitch.vue'
import { KINDS } from '../kinds'
import { relative } from '../time'

const OFFSET_PRESETS = [5, 10, 15, 30, 60, 120, 1440]

const sources = ref<IcsSource[]>([])
const loading = ref(true)
const error = ref('')
const formError = ref('')
const sheetOpen = ref(false)
const saving = ref(false)

function blankForm(): IcsSourceInput {
  return {
    url_or_path: '',
    offsets_minutes: [30, 15],
    refresh_minutes: 15,
    enabled: true,
    kind: 'appointment',
    dismissible: true,
    snooze_minutes: [],
  }
}

const form = reactive<IcsSourceInput>(blankForm())
const editingId = ref<string | null>(null)

async function refresh() {
  error.value = ''
  try {
    sources.value = await listIcsSources()
  } catch (e) {
    error.value = "Couldn't load your calendars. Try again in a moment."
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

/** A readable name from a feed URL or path: "calendar.google.com · basic.ics". */
function displayName(s: IcsSource): string {
  try {
    const u = new URL(s.url_or_path)
    const file = u.pathname.split('/').filter(Boolean).pop()
    return file ? `${u.hostname} · ${decodeURIComponent(file)}` : u.hostname
  } catch {
    return s.url_or_path.split('/').pop() || s.url_or_path
  }
}

function fmtOffset(m: number): string {
  if (m < 60) return `${m} min`
  if (m % 1440 === 0) return `${m / 1440} day${m === 1440 ? '' : 's'}`
  return m % 60 ? `${Math.floor(m / 60)} h ${m % 60}` : `${m / 60} h`
}

function offsetsSentence(offsets: number[]): string {
  if (!offsets.length) return 'No heads-up set'
  const sorted = [...offsets].sort((a, b) => b - a).map(fmtOffset)
  const list = sorted.length > 1 ? `${sorted.slice(0, -1).join(', ')} and ${sorted.at(-1)}` : sorted[0]
  return `Reminds you ${list} before`
}

function openCreate() {
  Object.assign(form, blankForm())
  editingId.value = null
  formError.value = ''
  sheetOpen.value = true
}

function openEdit(s: IcsSource) {
  Object.assign(form, {
    url_or_path: s.url_or_path,
    offsets_minutes: [...s.offsets_minutes],
    refresh_minutes: s.refresh_minutes,
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
  if (!form.offsets_minutes.length) {
    formError.value = 'Pick at least one time to be reminded before events.'
    return
  }
  if (!form.dismissible && form.snooze_minutes.length === 0) {
    formError.value = 'Pick a snooze option or allow dismissing, otherwise it could never be cleared.'
    return
  }
  saving.value = true
  formError.value = ''
  try {
    if (editingId.value) await updateIcsSource(editingId.value, form)
    else await createIcsSource(form)
    sheetOpen.value = false
    await refresh()
  } catch (e: any) {
    formError.value = e?.response?.data?.detail ?? "Couldn't save. Check the address and try again."
  } finally {
    saving.value = false
  }
}

async function remove() {
  if (!editingId.value) return
  try {
    await deleteIcsSource(editingId.value)
    sheetOpen.value = false
    await refresh()
  } catch {
    formError.value = "Couldn't delete. Try again."
  }
}

async function setEnabled(s: IcsSource, enabled: boolean) {
  s.enabled = enabled
  try {
    await updateIcsSource(s.id, { enabled })
  } catch {
    s.enabled = !enabled
    error.value = "Couldn't change that calendar. Try again."
  }
}
</script>

<template>
  <div>
    <PageHeader title="Calendars" subtitle="Get a heads-up on your watch before each event in your calendar.">
      <button v-if="sources.length" class="btn btn-primary" @click="openCreate"><AppIcon name="plus" /> Add calendar</button>
    </PageHeader>

    <p v-if="error" class="error-box mb-4" role="alert">{{ error }}</p>

    <div v-if="loading" class="space-y-3" aria-busy="true">
      <div v-for="i in 2" :key="i" class="card h-20 animate-pulse" />
    </div>

    <EmptyState
      v-else-if="!sources.length"
      icon="calendar"
      title="No calendars yet"
      text="Paste the private iCal / ICS link of your calendar, and you'll be reminded before each event."
    >
      <button class="btn btn-primary" @click="openCreate"><AppIcon name="plus" /> Add a calendar</button>
    </EmptyState>

    <ul v-else class="space-y-2">
      <li
        v-for="s in sources"
        :key="s.id"
        class="card !p-0 flex items-stretch overflow-hidden transition-opacity"
        :class="{ 'opacity-55': !s.enabled }"
      >
        <span class="w-1.5 shrink-0" :class="s.enabled ? KINDS[s.kind].stripe : 'bg-stone-300 dark:bg-stone-700'" aria-hidden="true" />
        <button
          type="button"
          class="flex flex-1 items-center gap-4 px-4 py-3.5 text-left min-w-0 hover:bg-stone-50 dark:hover:bg-stone-800/50"
          :aria-label="`Edit ${displayName(s)}`"
          @click="openEdit(s)"
        >
          <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl" :class="KINDS[s.kind].badge">
            <AppIcon name="calendar" :size="22" />
          </span>
          <span class="min-w-0 flex-1">
            <span class="block font-semibold truncate" :title="s.url_or_path">{{ displayName(s) }}</span>
            <span class="block text-sm muted">{{ offsetsSentence(s.offsets_minutes) }}</span>
            <span class="block text-xs muted mt-0.5">
              {{ s.last_synced_at ? `Updated ${relative(s.last_synced_at)}` : 'Not checked yet' }}
            </span>
          </span>
          <AppIcon name="pencil" :size="18" class="muted shrink-0 hidden sm:block" />
        </button>
        <div class="flex items-center pr-4 pl-1">
          <ToggleSwitch
            :model-value="s.enabled"
            :label="s.enabled ? `Turn off ${displayName(s)}` : `Turn on ${displayName(s)}`"
            hide-label
            @update:model-value="(v: boolean) => setEnabled(s, v)"
          />
        </div>
      </li>
    </ul>

    <EditSheet :open="sheetOpen" :title="editingId ? 'Edit calendar' : 'Add a calendar'" @close="sheetOpen = false">
      <form class="space-y-6" @submit.prevent="submit">
        <div>
          <label for="url" class="field-label">Calendar link</label>
          <input
            id="url"
            v-model="form.url_or_path"
            required
            autofocus
            placeholder="https://calendar.example.com/me.ics"
            class="field"
          />
          <p class="field-hint">Look for "secret address in iCal format" or "ICS link" in your calendar's settings.</p>
        </div>

        <div>
          <span id="offsets-label" class="field-label">Remind me before each event</span>
          <MinutesPicker v-model="form.offsets_minutes" labelledby="offsets-label" :presets="OFFSET_PRESETS" />
        </div>

        <ReminderOptions
          :kind="form.kind"
          :dismissible="form.dismissible"
          :snooze-minutes="form.snooze_minutes"
          @update:kind="(v: ReminderKind) => (form.kind = v)"
          @update:dismissible="(v: boolean) => (form.dismissible = v)"
          @update:snooze-minutes="(v: number[]) => (form.snooze_minutes = v)"
        />

        <details class="rounded-2xl border-2 border-stone-200 dark:border-stone-800 px-4 py-3">
          <summary class="font-semibold">Advanced</summary>
          <div class="mt-3">
            <label for="refresh" class="field-label">Check the calendar for changes every</label>
            <div class="flex items-center gap-2">
              <input id="refresh" v-model.number="form.refresh_minutes" type="number" min="1" required class="field !w-24" />
              <span>minutes</span>
            </div>
          </div>
        </details>

        <p v-if="formError" class="error-box" role="alert">{{ formError }}</p>

        <div class="flex flex-wrap items-center gap-3 pt-2">
          <button type="submit" :disabled="saving" class="btn btn-primary flex-1 sm:flex-none">
            {{ saving ? 'Saving…' : editingId ? 'Save changes' : 'Add calendar' }}
          </button>
          <button type="button" class="btn btn-ghost" @click="sheetOpen = false">Cancel</button>
          <DeleteButton v-if="editingId" class="sm:ml-auto" @confirm="remove" />
        </div>
      </form>
    </EditSheet>
  </div>
</template>
