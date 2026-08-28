<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
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
import ReminderOptions from '../components/ReminderOptions.vue'
import { btnDanger, btnPrimary, btnSecondary, card, errorText, input, label, muted } from '../ui'

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
const showForm = ref(false)
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

const pickerEl = ref<HTMLDivElement | null>(null)
let pickerMap: L.Map | null = null
let pickerMarker: L.Marker | null = null
let pickerCircle: L.Circle | null = null

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
}

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
    pickerCircle = L.circle(latlng, { radius, color: '#6366f1', fillOpacity: 0.15 }).addTo(pickerMap)
  } else {
    pickerCircle.setLatLng(latlng)
    pickerCircle.setRadius(radius)
  }
}

function onRadiusChange() {
  syncPickerMarker()
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    lists.value = await listTodoLists()
  } catch (e) {
    error.value = 'Could not load todo lists'
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

onBeforeUnmount(() => {
  pickerMap?.remove()
  pickerMap = null
})

async function startCreate() {
  Object.assign(form, blankForm())
  editingId.value = null
  showForm.value = true
  testStatus.value = 'idle'
  testDetail.value = ''
  pickerMap?.remove()
  pickerMap = null
  pickerMarker = null
  pickerCircle = null
  await nextTick()
  renderPicker()
}

async function startEdit(l: TodoList) {
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
  showForm.value = true
  testStatus.value = 'idle'
  testDetail.value = ''
  pickerMap?.remove()
  pickerMap = null
  pickerMarker = null
  pickerCircle = null
  await nextTick()
  renderPicker()
}

function cancelForm() {
  showForm.value = false
  editingId.value = null
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

async function submitForm() {
  if (!form.dismissible && form.snooze_minutes.length === 0) {
    error.value = 'Add a snooze option or make the reminder dismissible'
    return
  }
  saving.value = true
  error.value = ''
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
    showForm.value = false
    await refresh()
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? 'Could not save todo list'
  } finally {
    saving.value = false
  }
}

async function remove(l: TodoList) {
  if (!confirm(`Delete todo list "${l.name}"?`)) return
  await deleteTodoList(l.id)
  await refresh()
}

async function toggleEnabled(l: TodoList) {
  await updateTodoList(l.id, { enabled: !l.enabled })
  await refresh()
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

function formatSynced(iso: string | null): string {
  if (!iso) return 'never synced'
  return `synced ${new Date(iso).toLocaleString()}`
}
</script>

<template>
  <div>
    <div class="flex justify-between items-center">
      <h2 class="text-base font-semibold">Todo Lists</h2>
      <button v-if="!showForm" :class="btnPrimary" @click="startCreate">+ New list</button>
    </div>
    <p :class="[muted, 'mb-4']">
      Syncs a CalDAV todo list. Optionally tie it to a place - the first time your phone reports a
      position within range, you'll get a reminder listing what's still on the list.
    </p>

    <div v-if="showForm" :class="card">
      <h3 class="font-semibold mb-3">{{ editingId ? 'Edit list' : 'New list' }}</h3>
      <form class="space-y-4" @submit.prevent="submitForm">
        <div>
          <label for="name" :class="label">Name</label>
          <input id="name" v-model="form.name" required placeholder="Groceries" :class="[input, 'w-full']" />
        </div>

        <div>
          <label for="caldav_url" :class="label">CalDAV calendar URL</label>
          <input
            id="caldav_url"
            v-model="form.caldav_url"
            required
            placeholder="https://caldav.example.com/calendars/me/groceries/"
            :class="[input, 'w-full']"
          />
        </div>

        <div class="flex gap-3 flex-wrap">
          <div>
            <label for="username" :class="label">Username</label>
            <input id="username" v-model="form.username" :class="input" />
          </div>
          <div>
            <label for="password" :class="label">Password</label>
            <input
              id="password"
              v-model="form.password"
              type="password"
              :placeholder="editingId ? 'Leave blank to keep current' : ''"
              :class="input"
            />
          </div>
          <div>
            <label :class="label">&nbsp;</label>
            <button
              type="button"
              :class="[btnSecondary, 'block']"
              :disabled="!form.caldav_url || testStatus === 'testing'"
              @click="testConnection"
            >
              {{ testStatus === 'testing' ? 'Testing…' : 'Test connection' }}
            </button>
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

        <p v-if="testStatus === 'ok'" class="text-sm text-green-600 dark:text-green-400">Connected successfully.</p>
        <p v-else-if="testStatus === 'failed'" :class="errorText">Could not connect{{ testDetail ? `: ${testDetail}` : '' }}</p>

        <div>
          <div class="flex justify-between items-center mb-1">
            <label :class="label">Place (optional)</label>
            <button v-if="hasPlace" type="button" :class="[btnSecondary, 'text-xs px-2 py-1']" @click="clearPlace">
              Remove place
            </button>
          </div>
          <p :class="[muted, 'mb-2']">Click the map to set a place, drag the marker to adjust it.</p>
          <div ref="pickerEl" class="h-72 rounded-lg overflow-hidden border border-neutral-300 dark:border-neutral-700"></div>

          <div v-if="hasPlace" class="flex gap-3 flex-wrap mt-3">
            <div>
              <label for="place_label" :class="label">Label</label>
              <input id="place_label" v-model="form.place_label" placeholder="The store" :class="input" />
            </div>
            <div>
              <label for="place_radius" :class="label">
                Notify within {{ form.place_radius_m ?? 200 }}m
              </label>
              <input
                id="place_radius"
                v-model.number="form.place_radius_m"
                type="range"
                min="100"
                max="5000"
                step="100"
                class="w-48 align-middle"
                @input="onRadiusChange"
              />
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
    <p v-else-if="!lists.length && !showForm" :class="muted">No todo lists yet.</p>

    <div v-for="l in lists" :key="l.id" :class="card">
      <div class="flex justify-between items-center flex-wrap gap-3">
        <div>
          <div class="font-semibold" :class="{ 'opacity-50 line-through': !l.enabled }">{{ l.name }}</div>
          <div :class="muted">
            {{ l.place_latitude !== null ? `📍 ${l.place_label || 'place set'} (${l.place_radius_m}m) · ` : '' }}
            every {{ l.refresh_minutes }}m · {{ l.kind }} · {{ formatSynced(l.last_synced_at) }}
          </div>
        </div>
        <div class="flex gap-3">
          <button :class="btnSecondary" @click="toggleItems(l)">
            {{ expandedId === l.id ? 'Hide items' : 'Show items' }}
          </button>
          <button :class="btnSecondary" @click="toggleEnabled(l)">{{ l.enabled ? 'Disable' : 'Enable' }}</button>
          <button :class="btnSecondary" @click="startEdit(l)">Edit</button>
          <button :class="btnDanger" @click="remove(l)">Delete</button>
        </div>
      </div>

      <div v-if="expandedId === l.id" class="mt-3 pt-3 border-t border-neutral-200 dark:border-neutral-700">
        <p v-if="itemsLoading" :class="muted">Loading items…</p>
        <p v-else-if="!items.length" :class="muted">No items synced yet.</p>
        <ul v-else class="space-y-1">
          <li v-for="i in items" :key="i.id" class="text-sm flex items-center gap-2">
            <span :class="{ 'line-through opacity-50': i.completed }">{{ i.summary }}</span>
            <span v-if="i.due" :class="muted">· due {{ new Date(i.due).toLocaleString() }}</span>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>
