<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Chart,
  LinearScale,
  LineController,
  LineElement,
  PointElement,
  TimeScale,
  Tooltip,
  type ChartOptions,
} from 'chart.js'
import annotationPlugin, { type AnnotationOptions } from 'chartjs-plugin-annotation'
import 'chartjs-adapter-date-fns'
import { listHeartRate, listNotifications, type HeartRateReading, type Notification } from '../api'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import SegmentedControl from '../components/SegmentedControl.vue'

Chart.register(LineController, LineElement, PointElement, LinearScale, TimeScale, Tooltip, annotationPlugin)

interface Range {
  key: string
  label: string
  hours: number
  unit: 'hour' | 'day'
}

const RANGES: Range[] = [
  { key: 'daily', label: 'Day', hours: 24, unit: 'hour' },
  { key: '3day', label: '3 days', hours: 72, unit: 'day' },
  { key: 'weekly', label: 'Week', hours: 24 * 7, unit: 'day' },
]

const selectedRange = ref<Range>(RANGES[0])
const rangeKey = computed({
  get: () => selectedRange.value.key,
  set: (k: string) => (selectedRange.value = RANGES.find((r) => r.key === k) ?? RANGES[0]),
})
const rangeOptions = RANGES.map((r) => ({ value: r.key, label: r.label }))
const readings = ref<HeartRateReading[]>([])
const medicationAcks = ref<Notification[]>([])
const loading = ref(true)
const error = ref('')
const average = ref<number | null>(null)

const canvasEl = ref<HTMLCanvasElement | null>(null)
let chart: Chart<'line', { x: number; y: number }[]> | null = null

function isDarkMode(): boolean {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const until = new Date()
    const since = new Date(until.getTime() - selectedRange.value.hours * 60 * 60 * 1000)
    const [heartRate, notifications] = await Promise.all([listHeartRate(since, until), listNotifications()])
    readings.value = heartRate
    average.value = heartRate.length
      ? Math.round(heartRate.reduce((sum, r) => sum + r.bpm, 0) / heartRate.length)
      : null
    // "Marked as DONE" = the watch's DONE button, which produces a `dismissed` ack - a `snoozed`
    // one means they haven't taken it yet, so it doesn't belong on the chart.
    medicationAcks.value = notifications.filter((n): n is Notification & { acked_at: string } => {
      if (n.kind !== 'medication' || n.ack_action !== 'dismissed' || !n.acked_at) return false
      const at = new Date(n.acked_at)
      return at >= since && at <= until
    })
  } catch (e) {
    error.value = 'Could not load heart rate data'
  } finally {
    loading.value = false
    renderChart()
  }
}

onMounted(refresh)
watch(selectedRange, refresh)

function renderChart() {
  if (!canvasEl.value) return
  const dark = isDarkMode()
  const gridColor = dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'
  const tickColor = dark ? '#a3a3a3' : '#737373'

  const annotations: Record<string, AnnotationOptions> = {}

  if (average.value != null) {
    annotations.average = {
      type: 'line',
      scaleID: 'y',
      value: average.value,
      borderColor: '#f59e0b',
      borderWidth: 1.5,
      borderDash: [6, 6],
      label: {
        display: true,
        content: `avg ${average.value} bpm`,
        position: 'end',
        backgroundColor: '#f59e0b',
        color: '#fff',
        font: { size: 11 },
        padding: 4,
      },
    }
  }

  medicationAcks.value.forEach((n, i) => {
    annotations[`med-${i}`] = {
      type: 'line',
      scaleID: 'x',
      value: new Date(n.acked_at as string).getTime(),
      borderColor: '#10b981',
      borderWidth: 1.5,
      label: {
        display: true,
        content: '💊',
        position: 'start',
        backgroundColor: 'transparent',
        font: { size: 13 },
      },
    }
  })

  const data = {
    datasets: [
      {
        label: 'Heart rate',
        data: readings.value.map((r) => ({ x: new Date(r.recorded_at).getTime(), y: r.bpm })),
        borderColor: '#e11d48',
        backgroundColor: '#e11d48',
        pointRadius: readings.value.length > 150 ? 0 : 2,
        borderWidth: 2,
        tension: 0.25,
      },
    ],
  }

  const options: ChartOptions<'line'> = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    scales: {
      x: {
        type: 'time',
        time: { unit: selectedRange.value.unit },
        ticks: { color: tickColor },
        grid: { color: gridColor },
      },
      y: {
        title: { display: true, text: 'bpm', color: tickColor },
        ticks: { color: tickColor },
        grid: { color: gridColor },
      },
    },
    plugins: {
      legend: { display: false },
      annotation: { annotations },
    },
  }

  if (chart) {
    chart.data = data
    chart.options = options
    chart.update()
  } else {
    chart = new Chart(canvasEl.value, { type: 'line', data, options })
  }
}

onBeforeUnmount(() => {
  chart?.destroy()
  chart = null
})
</script>

<template>
  <div>
    <PageHeader title="Heart rate" subtitle="Readings from your watch. The 💊 lines show when you marked a medication as done.">
      <SegmentedControl v-model="rangeKey" :options="rangeOptions" label="Time range" />
    </PageHeader>

    <p v-if="error" class="error-box mb-4" role="alert">{{ error }}</p>
    <div v-else-if="loading" class="card h-80 animate-pulse" aria-busy="true" />
    <EmptyState v-else-if="!readings.length" icon="heart" title="No readings yet" text="Nothing from your watch in this time range." />

    <div v-show="!loading && !error && readings.length" class="space-y-4">
      <div v-if="average != null" class="grid grid-cols-2 gap-3">
        <div class="card">
          <p class="text-sm font-semibold muted">Average</p>
          <p class="text-3xl font-bold tabular-nums">{{ average }} <span class="text-base font-semibold muted">bpm</span></p>
        </div>
        <div class="card">
          <p class="text-sm font-semibold muted">Medication done</p>
          <p class="text-3xl font-bold tabular-nums">{{ medicationAcks.length }} <span class="text-base font-semibold muted">times</span></p>
        </div>
      </div>
      <div class="card">
        <div class="h-72">
          <canvas ref="canvasEl" aria-label="Heart rate chart" role="img"></canvas>
        </div>
        <p class="text-sm muted mt-3">{{ readings.length }} reading{{ readings.length === 1 ? '' : 's' }} in this range</p>
      </div>
    </div>
  </div>
</template>
