<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import { listLocations, ringPhone, type PhoneLocation } from '../api'
import { card, muted } from '../ui'

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
  { key: 'daily', label: 'Last 24h', hours: 24 },
  { key: '3day', label: 'Last 3 Days', hours: 72 },
  { key: 'weekly', label: 'Last Week', hours: 24 * 7 },
]

const selectedRange = ref<Range>(RANGES[0])
const locations = ref<PhoneLocation[]>([])
const loading = ref(true)
const error = ref('')

const mapEl = ref<HTMLDivElement | null>(null)
let map: L.Map | null = null
let trail: L.Polyline | null = null
let latestMarker: L.Marker | null = null

const ringStatus = ref<'idle' | 'ringing' | 'unreachable'>('idle')

async function ring() {
  ringStatus.value = 'ringing'
  try {
    const delivered = await ringPhone()
    ringStatus.value = delivered ? 'ringing' : 'unreachable'
  } catch (e) {
    ringStatus.value = 'unreachable'
  } finally {
    setTimeout(() => (ringStatus.value = 'idle'), 2000)
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

  trail = L.polyline(points, { color: '#6366f1', weight: 3, opacity: 0.6 }).addTo(map)

  const latest = locations.value[locations.value.length - 1]
  latestMarker = L.marker([latest.latitude, latest.longitude])
    .addTo(map)
    .bindPopup(`Last seen ${new Date(latest.recorded_at).toLocaleString()}`)
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
  <div>
    <div class="flex justify-between items-center flex-wrap gap-3">
      <h2 class="text-base font-semibold">Where's My Phone</h2>
      <div class="flex items-center gap-3 flex-wrap">
        <div class="flex gap-1.5">
          <button
            v-for="r in RANGES"
            :key="r.key"
            type="button"
            class="rounded-md px-3 py-1.5 text-sm"
            :class="
              selectedRange.key === r.key
                ? 'bg-indigo-600 text-white'
                : 'bg-transparent border border-neutral-300 dark:border-neutral-700 text-neutral-900 dark:text-neutral-100'
            "
            @click="selectRange(r)"
          >
            {{ r.label }}
          </button>
        </div>
        <button
          type="button"
          class="rounded-md px-3 py-1.5 text-sm bg-transparent border border-neutral-300 dark:border-neutral-700 text-neutral-900 dark:text-neutral-100 disabled:opacity-60"
          :disabled="ringStatus === 'ringing'"
          @click="ring"
        >
          {{ ringStatus === 'ringing' ? 'Ringing…' : ringStatus === 'unreachable' ? 'Phone unreachable' : 'Ring phone' }}
        </button>
      </div>
    </div>
    <p :class="[muted, 'mb-4']">
      Positions reported by the companion app roughly every 30 minutes. The line is just samples
      joined in order, not an actual route.
    </p>

    <p v-if="error" class="text-sm text-red-600 dark:text-red-400 mb-4">{{ error }}</p>
    <p v-else-if="!loading && !locations.length" :class="[muted, 'mb-4']">
      No location reported in this range yet.
    </p>

    <div :class="card">
      <div ref="mapEl" class="h-96 rounded-lg overflow-hidden"></div>
      <p v-if="locations.length" :class="[muted, 'mt-3']">
        Last seen {{ new Date(locations[locations.length - 1].recorded_at).toLocaleString() }}
        · {{ locations.length }} sample{{ locations.length === 1 ? '' : 's' }} in this range
      </p>
    </div>
  </div>
</template>
