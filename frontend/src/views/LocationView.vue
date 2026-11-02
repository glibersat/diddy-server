<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import { listLocations, ringPhone, type PhoneLocation } from '../api'
import AppIcon from '../components/AppIcon.vue'
import PageHeader from '../components/PageHeader.vue'
import SegmentedControl from '../components/SegmentedControl.vue'
import { friendlyDateTime, relative } from '../time'

// Vite doesn't rewrite Leaflet's built-in image URLs to hashed asset paths - point the default
// icon at the bundled assets explicitly, or markers render as broken images.
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

interface Range {
  key: string
  label: string
  hours: number
}

const RANGES: Range[] = [
  { key: 'daily', label: '24 h', hours: 24 },
  { key: '3day', label: '3 days', hours: 72 },
  { key: 'weekly', label: 'Week', hours: 24 * 7 },
]

const selectedRange = ref<Range>(RANGES[0])
const rangeKey = computed({
  get: () => selectedRange.value.key,
  set: (k: string) => selectRange(RANGES.find((r) => r.key === k) ?? RANGES[0]),
})
const rangeOptions = RANGES.map((r) => ({ value: r.key, label: r.label }))
const latest = computed(() => locations.value.at(-1) ?? null)
const locations = ref<PhoneLocation[]>([])
const loading = ref(true)
const error = ref('')

const mapEl = ref<HTMLDivElement | null>(null)
let map: L.Map | null = null
let trail: L.Polyline | null = null
let latestMarker: L.Marker | null = null

const ringStatus = ref<'idle' | 'sending' | 'ringing' | 'unreachable'>('idle')

async function ring() {
  ringStatus.value = 'sending'
  try {
    const delivered = await ringPhone()
    ringStatus.value = delivered ? 'ringing' : 'unreachable'
  } catch (e) {
    ringStatus.value = 'unreachable'
  } finally {
    setTimeout(() => (ringStatus.value = 'idle'), 3000)
  }
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const until = new Date()
    const since = new Date(until.getTime() - selectedRange.value.hours * 60 * 60 * 1000)
    locations.value = await listLocations(since, until)
  } catch (e) {
    error.value = 'Could not load location data'
  } finally {
    loading.value = false
    renderMap()
  }
}

function renderMap() {
  if (!mapEl.value) return

  if (!map) {
    map = L.map(mapEl.value).setView([0, 0], 2)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(map)
  }

  trail?.remove()
  latestMarker?.remove()
  trail = null
  latestMarker = null

  if (!locations.value.length) return

  const points: [number, number][] = locations.value.map((l) => [l.latitude, l.longitude])

  trail = L.polyline(points, { color: '#4f46e5', weight: 3, opacity: 0.6 }).addTo(map)

  const latest = locations.value[locations.value.length - 1]
  latestMarker = L.marker([latest.latitude, latest.longitude])
    .addTo(map)
    .bindPopup(`Last seen ${friendlyDateTime(latest.recorded_at)}`)
    .openPopup()

  map.fitBounds(trail.getBounds().pad(0.2), { maxZoom: 16 })
}

function selectRange(r: Range) {
  selectedRange.value = r
  refresh()
}

onMounted(refresh)

onBeforeUnmount(() => {
  map?.remove()
  map = null
})
</script>

<template>
  <div class="space-y-4">
    <PageHeader title="Find my phone" subtitle="Where your phone last reported its position (about every 30 minutes)." />

    <div class="card flex flex-wrap items-center gap-4">
      <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300">
        <AppIcon name="phone" :size="26" />
      </span>
      <div class="flex-1 min-w-40">
        <p class="font-semibold">{{ latest ? `Seen ${relative(latest.recorded_at)}` : 'No position yet' }}</p>
        <p class="text-sm muted">{{ latest ? friendlyDateTime(latest.recorded_at) : 'Nothing reported in this range.' }}</p>
      </div>
      <button type="button" class="btn btn-primary" :disabled="ringStatus === 'sending'" @click="ring">
        <AppIcon name="bell" :size="18" />
        {{
          ringStatus === 'sending'
            ? 'Calling…'
            : ringStatus === 'ringing'
              ? 'Ringing!'
              : ringStatus === 'unreachable'
                ? "Phone isn't connected"
                : 'Ring my phone'
        }}
      </button>
    </div>

    <p v-if="error" class="error-box" role="alert">{{ error }}</p>

    <div class="card !p-3 space-y-3">
      <div class="flex items-center justify-between gap-3 flex-wrap px-2 pt-1">
        <p class="text-sm muted">The line joins the reported points in order. It isn't the exact route.</p>
        <SegmentedControl v-model="rangeKey" :options="rangeOptions" label="Time range" />
      </div>
      <div ref="mapEl" class="h-96 rounded-xl overflow-hidden"></div>
      <p v-if="locations.length" class="text-sm muted px-2 pb-1">
        {{ locations.length }} point{{ locations.length === 1 ? '' : 's' }} in this range
      </p>
    </div>
  </div>
</template>
