<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
import { card, muted } from '../ui'

Chart.register(LineController, LineElement, PointElement, LinearScale, TimeScale, Tooltip, annotationPlugin)

interface Range {
  key: string
  label: string
  hours: number
  unit: 'hour' | 'day'
}

const RANGES: Range[] = [
  { key: 'daily', label: 'Daily', hours: 24, unit: 'hour' },
  { key: '3day', label: '3 Days', hours: 72, unit: 'day' },
  { key: 'weekly', label: 'Weekly', hours: 24 * 7, unit: 'day' },
]

const selectedRange = ref<Range>(RANGES[0])
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
        borderColor: '#6366f1',
        backgroundColor: '#6366f1',
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
    <div class="flex justify-between items-center flex-wrap gap-3">
      <h2 class="text-base font-semibold">Heart Rate</h2>
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
          @click="selectedRange = r"
        >
          {{ r.label }}
        </button>
      </div>
    </div>
    <p :class="[muted, 'mb-4']">
      Readings from the watch's Heart Rate Service - spot checks and periodic background samples
      alike. 💊 marks a medication reminder marked DONE, to see its effect on heart rate.
    </p>

    <p v-if="loading">Loading…</p>
    <p v-else-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    <p v-else-if="!readings.length" :class="muted">No heart rate readings in this range yet.</p>

    <div v-show="!loading && !error && readings.length" :class="card">
      <div class="h-72">
        <canvas ref="canvasEl"></canvas>
      </div>
      <p v-if="average != null" :class="[muted, 'mt-3']">
        Average: {{ average }} bpm over {{ readings.length }} reading{{ readings.length === 1 ? '' : 's' }}
        <span v-if="medicationAcks.length">
          · {{ medicationAcks.length }} medication dose{{ medicationAcks.length === 1 ? '' : 's' }} marked DONE in
          this range
        </span>
      </p>
    </div>
  </div>
</template>
