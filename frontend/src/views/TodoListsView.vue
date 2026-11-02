<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import {
  createTodoList,
  deleteTodoList,
  listTodoItems,
  listTodoLists,
  testTodoListConnection,
  updateTodoList,
  type ReminderKind,
  type TodoItem,
  type TodoList,
  type TodoListInput,
} from '../api'
import AppIcon from '../components/AppIcon.vue'
import DeleteButton from '../components/DeleteButton.vue'
import EditSheet from '../components/EditSheet.vue'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import ReminderOptions from '../components/ReminderOptions.vue'
import ToggleSwitch from '../components/ToggleSwitch.vue'
import { KINDS } from '../kinds'
import { friendlyDateTime, relative } from '../time'

// Vite doesn't rewrite Leaflet's built-in image URLs to hashed asset paths - point the default
// icon at the bundled assets explicitly, or markers render as broken images.
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

const DEFAULT_RADIUS_M = 200

const lists = ref<TodoList[]>([])
const loading = ref(true)
const error = ref('')
const formError = ref('')
const sheetOpen = ref(false)
const saving = ref(false)

const expandedId = ref<string | null>(null)
const items = ref<TodoItem[]>([])
const itemsLoading = ref(false)

function blankForm(): TodoListInput {
  return {
    name: '',
    caldav_url: '',
    username: '',
    password: '',
    refresh_minutes: 15,
    enabled: true,
    place_label: null,
    place_latitude: null,
    place_longitude: null,
    place_radius_m: null,
    kind: 'generic',
    dismissible: true,
    snooze_minutes: [],
  }
}

const form = reactive<TodoListInput>(blankForm())
const editingId = ref<string | null>(null)
const hasPlace = computed(() => form.place_latitude !== null && form.place_longitude !== null)
/** The "near a place" switch. The map only appears once it's on: one less thing to look at. */
const wantPlace = ref(false)

const pickerEl = ref<HTMLDivElement | null>(null)
let pickerMap: L.Map | null = null
let pickerMarker: L.Marker | null = null
let pickerCircle: L.Circle | null = null

function destroyPicker() {
  pickerMap?.remove()
  pickerMap = null
  pickerMarker = null
  pickerCircle = null
}

function renderPicker() {
  if (!pickerEl.value || pickerMap) return
  pickerMap = L.map(pickerEl.value).setView(
    hasPlace.value ? [form.place_latitude!, form.place_longitude!] : [48.8566, 2.3522],
    hasPlace.value ? 15 : 5,
  )
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(pickerMap)
  pickerMap.on('click', (e: L.LeafletMouseEvent) => setPlace(e.latlng.lat, e.latlng.lng))
  syncPickerMarker()
  // The sheet slides in: let Leaflet re-measure once it has settled, or tiles render half-grey.
  setTimeout(() => pickerMap?.invalidateSize(), 260)
}

watch(wantPlace, async (on) => {
  if (on) {
    await nextTick()
    renderPicker()
  } else {
    clearPlace()
    destroyPicker()
  }
})

function setPlace(lat: number, lng: number) {
  form.place_latitude = Math.round(lat * 1e6) / 1e6
  form.place_longitude = Math.round(lng * 1e6) / 1e6
  if (form.place_radius_m === null) form.place_radius_m = DEFAULT_RADIUS_M
  syncPickerMarker()
}

function clearPlace() {
  form.place_label = null
  form.place_latitude = null
  form.place_longitude = null
  form.place_radius_m = null
  pickerMarker?.remove()
  pickerCircle?.remove()
  pickerMarker = null
  pickerCircle = null
}

function syncPickerMarker() {
  if (!pickerMap || !hasPlace.value) return
  const latlng: L.LatLngExpression = [form.place_latitude!, form.place_longitude!]
  if (!pickerMarker) {
    pickerMarker = L.marker(latlng, { draggable: true }).addTo(pickerMap)
    pickerMarker.on('dragend', () => {
      const pos = pickerMarker!.getLatLng()
      setPlace(pos.lat, pos.lng)
    })
  } else {
    pickerMarker.setLatLng(latlng)
  }
  const radius = form.place_radius_m ?? DEFAULT_RADIUS_M
  if (!pickerCircle) {
    pickerCircle = L.circle(latlng, { radius, color: '#4f46e5', fillOpacity: 0.15 }).addTo(pickerMap)
  } else {
    pickerCircle.setLatLng(latlng)
    pickerCircle.setRadius(radius)
  }
}

async function refresh() {
  error.value = ''
  try {
    lists.value = await listTodoLists()
  } catch (e) {
    error.value = "Couldn't load your lists. Try again in a moment."
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
onBeforeUnmount(destroyPicker)

async function openSheet() {
  testStatus.value = 'idle'
  testDetail.value = ''
  formError.value = ''
  destroyPicker()
  wantPlace.value = hasPlace.value
  sheetOpen.value = true
  if (wantPlace.value) {
    await nextTick()
    renderPicker()
  }
}

function openCreate() {
  Object.assign(form, blankForm())
  editingId.value = null
  openSheet()
}

function openEdit(l: TodoList) {
  Object.assign(form, {
    name: l.name,
    caldav_url: l.caldav_url,
    username: l.username ?? '',
    password: '',
    refresh_minutes: l.refresh_minutes,
    enabled: l.enabled,
    place_label: l.place_label,
    place_latitude: l.place_latitude,
    place_longitude: l.place_longitude,
    place_radius_m: l.place_radius_m,
    kind: l.kind,
    dismissible: l.dismissible,
    snooze_minutes: [...l.snooze_minutes],
  })
  editingId.value = l.id
  openSheet()
}

function closeSheet() {
  sheetOpen.value = false
  destroyPicker()
}

const testStatus = ref<'idle' | 'testing' | 'ok' | 'failed'>('idle')
const testDetail = ref('')

async function testConnection() {
  testStatus.value = 'testing'
  testDetail.value = ''
  try {
    const result = await testTodoListConnection(form.caldav_url, form.username || null, form.password || null)
    testStatus.value = result.ok ? 'ok' : 'failed'
    testDetail.value = result.detail ?? ''
  } catch (e: any) {
    testStatus.value = 'failed'
    testDetail.value = e?.response?.data?.detail ?? 'Could not reach the server'
  }
}

async function submit() {
  if (wantPlace.value && !hasPlace.value) {
    formError.value = 'Tap the map to choose the place, or turn off "Remind me near a place".'
    return
  }
  if (!form.dismissible && form.snooze_minutes.length === 0) {
    formError.value = 'Pick a snooze option or allow dismissing, otherwise it could never be cleared.'
    return
  }
  saving.value = true
  formError.value = ''
  try {
    if (editingId.value) {
      const clearingPlace = !hasPlace.value
      // Blank password means "unchanged" on edit, not "clear it" - unlike every other field,
      // omitting it from the payload (rather than sending "") is what keeps the stored value.
      const { password, ...rest } = form
      const patch = password ? form : rest
      await updateTodoList(editingId.value, patch, clearingPlace)
    } else {
      await createTodoList(form)
    }
    closeSheet()
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
    await deleteTodoList(editingId.value)
    closeSheet()
    await refresh()
  } catch {
    formError.value = "Couldn't delete. Try again."
  }
}

async function setEnabled(l: TodoList, enabled: boolean) {
  l.enabled = enabled
  try {
    await updateTodoList(l.id, { enabled })
  } catch {
    l.enabled = !enabled
    error.value = "Couldn't change that list. Try again."
  }
}

async function toggleItems(l: TodoList) {
  if (expandedId.value === l.id) {
    expandedId.value = null
    return
  }
  expandedId.value = l.id
  itemsLoading.value = true
  try {
    items.value = await listTodoItems(l.id)
  } catch (e) {
    items.value = []
  } finally {
    itemsLoading.value = false
  }
}

const pendingItems = computed(() => items.value.filter((i) => !i.completed))
const doneItems = computed(() => items.value.filter((i) => i.completed))
</script>

<template>
  <div>
    <PageHeader title="Lists" subtitle="Your todo lists. Tie one to a place and get it on your watch when you arrive.">
      <button v-if="lists.length" class="btn btn-primary" @click="openCreate"><AppIcon name="plus" /> New list</button>
    </PageHeader>

    <p v-if="error" class="error-box mb-4" role="alert">{{ error }}</p>

    <div v-if="loading" class="space-y-3" aria-busy="true">
      <div v-for="i in 2" :key="i" class="card h-20 animate-pulse" />
    </div>

    <EmptyState
      v-else-if="!lists.length"
      icon="list"
      title="No lists yet"
      text="Connect a todo list (CalDAV). Example: your groceries list pops up when you get near the store."
    >
      <button class="btn btn-primary" @click="openCreate"><AppIcon name="plus" /> Connect a list</button>
    </EmptyState>

    <ul v-else class="space-y-2">
      <li v-for="l in lists" :key="l.id" class="card !p-0 overflow-hidden transition-opacity" :class="{ 'opacity-55': !l.enabled }">
        <div class="flex items-stretch">
          <span class="w-1.5 shrink-0" :class="l.enabled ? KINDS[l.kind].stripe : 'bg-stone-300 dark:bg-stone-700'" aria-hidden="true" />
          <button
            type="button"
            class="flex flex-1 items-center gap-4 px-4 py-3.5 text-left min-w-0 hover:bg-stone-50 dark:hover:bg-stone-800/50"
            :aria-label="`Edit ${l.name}`"
            @click="openEdit(l)"
          >
            <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl" :class="KINDS[l.kind].badge">
              <AppIcon :name="l.place_latitude !== null ? 'pin' : 'list'" :size="22" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block font-semibold truncate">{{ l.name }}</span>
              <span class="block text-sm muted">
                {{ l.place_latitude !== null ? `Near ${l.place_label || 'your place'} (${l.place_radius_m} m)` : 'No place set' }}
              </span>
              <span class="block text-xs muted mt-0.5">
                {{ l.last_synced_at ? `Updated ${relative(l.last_synced_at)}` : 'Not synced yet' }}
              </span>
            </span>
            <AppIcon name="pencil" :size="18" class="muted shrink-0 hidden sm:block" />
          </button>
          <div class="flex items-center pr-4 pl-1">
            <ToggleSwitch
              :model-value="l.enabled"
              :label="l.enabled ? `Turn off ${l.name}` : `Turn on ${l.name}`"
              hide-label
              @update:model-value="(v: boolean) => setEnabled(l, v)"
            />
          </div>
        </div>

        <button
          type="button"
          class="w-full flex items-center gap-2 border-t border-stone-100 dark:border-stone-800 px-5 py-2.5 text-sm font-semibold text-indigo-700 dark:text-indigo-300 hover:bg-stone-50 dark:hover:bg-stone-800/50"
          :aria-expanded="expandedId === l.id"
          @click="toggleItems(l)"
        >
          <AppIcon name="chevron-down" :size="18" class="transition-transform" :class="{ 'rotate-180': expandedId === l.id }" />
          {{ expandedId === l.id ? 'Hide items' : 'Show items' }}
        </button>

        <div v-if="expandedId === l.id" class="px-5 pb-4">
          <p v-if="itemsLoading" class="muted">Loading items…</p>
          <p v-else-if="!items.length" class="muted">Nothing on this list yet.</p>
          <template v-else>
            <ul class="space-y-1.5">
              <li v-for="i in pendingItems" :key="i.id" class="flex items-start gap-2.5">
                <span class="mt-1.5 h-4 w-4 shrink-0 rounded-md border-2 border-stone-300 dark:border-stone-600" aria-hidden="true" />
                <span>
                  {{ i.summary }}
                  <span v-if="i.due" class="text-sm muted"> · due {{ friendlyDateTime(i.due) }}</span>
                </span>
              </li>
            </ul>
            <p v-if="doneItems.length" class="text-sm muted mt-3">
              <AppIcon name="check" :size="14" class="inline -mt-0.5" /> {{ doneItems.length }} done
            </p>
          </template>
        </div>
      </li>
    </ul>

    <EditSheet :open="sheetOpen" :title="editingId ? 'Edit list' : 'Connect a list'" @close="closeSheet">
      <form class="space-y-6" @submit.prevent="submit">
        <div>
          <label for="name" class="field-label">Name</label>
          <input id="name" v-model="form.name" required autofocus placeholder="Groceries" class="field text-lg" />
        </div>

        <fieldset class="space-y-4 rounded-2xl border-2 border-stone-200 dark:border-stone-800 p-4">
          <legend class="px-1 font-semibold">Connection</legend>
          <div>
            <label for="caldav_url" class="field-label">CalDAV list address</label>
            <input
              id="caldav_url"
              v-model="form.caldav_url"
              required
              placeholder="https://caldav.example.com/calendars/me/groceries/"
              class="field"
            />
          </div>
          <div class="grid gap-4 sm:grid-cols-2">
            <div>
              <label for="username" class="field-label">Username</label>
              <input id="username" v-model="form.username" autocomplete="username" class="field" />
            </div>
            <div>
              <label for="password" class="field-label">Password</label>
              <input
                id="password"
                v-model="form.password"
                type="password"
                autocomplete="current-password"
                :placeholder="editingId ? 'Unchanged' : ''"
                class="field"
              />
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-3">
            <button
              type="button"
              class="btn btn-secondary"
              :disabled="!form.caldav_url || testStatus === 'testing'"
              @click="testConnection"
            >
              {{ testStatus === 'testing' ? 'Checking…' : 'Check connection' }}
            </button>
            <span v-if="testStatus === 'ok'" class="font-semibold text-emerald-700 dark:text-emerald-300 inline-flex items-center gap-1.5">
              <AppIcon name="check" :size="18" /> Connected
            </span>
          </div>
          <p v-if="testStatus === 'failed'" class="error-box text-sm" role="alert">
            Couldn't connect{{ testDetail ? `: ${testDetail}` : '' }}
          </p>
        </fieldset>

        <div class="space-y-3">
          <ToggleSwitch v-model="wantPlace" label="Remind me when I get near a place" />
          <div v-if="wantPlace" class="space-y-3">
            <p class="text-sm muted">Tap the map to choose the place. Drag the pin to adjust it.</p>
            <div ref="pickerEl" class="h-72 rounded-2xl overflow-hidden border-2 border-stone-200 dark:border-stone-800" />
            <div v-if="hasPlace" class="grid gap-4 sm:grid-cols-2">
              <div>
                <label for="place_label" class="field-label">Place name</label>
                <input id="place_label" v-model="form.place_label" placeholder="The store" class="field" />
              </div>
              <div>
                <label for="place_radius" class="field-label">Within {{ form.place_radius_m ?? DEFAULT_RADIUS_M }} m</label>
                <input
                  id="place_radius"
                  v-model.number="form.place_radius_m"
                  type="range"
                  min="100"
                  max="5000"
                  step="100"
                  class="w-full h-11 accent-indigo-600"
                  @input="syncPickerMarker"
                />
              </div>
            </div>
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

        <details class="rounded-2xl border-2 border-stone-200 dark:border-stone-800 px-4 py-3">
          <summary class="font-semibold">Advanced</summary>
          <div class="mt-3">
            <label for="refresh" class="field-label">Sync the list every</label>
            <div class="flex items-center gap-2">
              <input id="refresh" v-model.number="form.refresh_minutes" type="number" min="1" required class="field !w-24" />
              <span>minutes</span>
            </div>
          </div>
        </details>

        <p v-if="formError" class="error-box" role="alert">{{ formError }}</p>

        <div class="flex flex-wrap items-center gap-3 pt-2">
          <button type="submit" :disabled="saving" class="btn btn-primary flex-1 sm:flex-none">
            {{ saving ? 'Saving…' : editingId ? 'Save changes' : 'Connect list' }}
          </button>
          <button type="button" class="btn btn-ghost" @click="closeSheet">Cancel</button>
          <DeleteButton v-if="editingId" class="sm:ml-auto" @confirm="remove" />
        </div>
      </form>
    </EditSheet>
  </div>
</template>
