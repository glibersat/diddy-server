<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  createIcsSource,
  deleteIcsSource,
  listIcsSources,
  updateIcsSource,
  type IcsSource,
  type IcsSourceInput,
  type ReminderKind,
} from '../api'
import ReminderOptions from '../components/ReminderOptions.vue'
import { btnDanger, btnPrimary, btnSecondary, card, errorText, input, label, muted } from '../ui'

const sources = ref<IcsSource[]>([])
const loading = ref(true)
const error = ref('')
const showForm = ref(false)
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

const offsetsText = computed({
  get: () => form.offsets_minutes.join(', '),
  set: (val: string) => {
    form.offsets_minutes = val
      .split(',')
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !Number.isNaN(n))
  },
})

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    sources.value = await listIcsSources()
  } catch (e) {
    error.value = 'Could not load ICS sources'
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

function startEdit(s: IcsSource) {
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
      await updateIcsSource(editingId.value, form)
    } else {
      await createIcsSource(form)
    }
    showForm.value = false
    await refresh()
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? 'Could not save ICS source'
  } finally {
    saving.value = false
  }
}

async function remove(s: IcsSource) {
  if (!confirm(`Delete ICS source "${s.url_or_path}"?`)) return
  await deleteIcsSource(s.id)
  await refresh()
}

async function toggleEnabled(s: IcsSource) {
  await updateIcsSource(s.id, { enabled: !s.enabled })
  await refresh()
}

function formatSynced(iso: string | null): string {
  if (!iso) return 'never synced'
  return `synced ${new Date(iso).toLocaleString()}`
}
</script>

<template>
  <div>
    <div class="flex justify-between items-center">
      <h2 class="text-base font-semibold">ICS Sources</h2>
      <button v-if="!showForm" :class="btnPrimary" @click="startCreate">+ New source</button>
    </div>
    <p :class="[muted, 'mb-4']">Reminds you N minutes before each event in a personal calendar export.</p>

    <div v-if="showForm" :class="card">
      <h3 class="font-semibold mb-3">{{ editingId ? 'Edit source' : 'New source' }}</h3>
      <form class="space-y-4" @submit.prevent="submitForm">
        <div>
          <label for="url" :class="label">ICS URL or file path</label>
          <input
            id="url"
            v-model="form.url_or_path"
            required
            placeholder="https://calendar.example.com/me.ics"
            :class="[input, 'w-full']"
          />
        </div>

        <div class="flex gap-3 flex-wrap">
          <div>
            <label for="offsets" :class="label">Remind before event (minutes, comma separated)</label>
            <input id="offsets" v-model="offsetsText" placeholder="30, 15" :class="input" />
          </div>
          <div>
            <label for="refresh" :class="label">Refresh every (minutes)</label>
            <input
              id="refresh"
              v-model.number="form.refresh_minutes"
              type="number"
              min="1"
              required
              :class="input"
            />
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
    <p v-else-if="!sources.length && !showForm" :class="muted">No ICS sources yet.</p>

    <div
      v-for="s in sources"
      :key="s.id"
      :class="[card, 'flex justify-between items-center flex-wrap gap-3']"
    >
      <div>
        <div class="font-semibold break-all" :class="{ 'opacity-50 line-through': !s.enabled }">
          {{ s.url_or_path }}
        </div>
        <div :class="muted">
          {{ s.offsets_minutes.join('/') }}m before · every {{ s.refresh_minutes }}m · {{ s.kind }} ·
          {{ formatSynced(s.last_synced_at) }}
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
