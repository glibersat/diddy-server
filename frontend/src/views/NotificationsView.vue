<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listNotifications, type Notification } from '../api'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import PageHeader from '../components/PageHeader.vue'
import SegmentedControl from '../components/SegmentedControl.vue'
import { KINDS, headline } from '../kinds'
import { clock, friendlyDateTime } from '../time'

type ViewMode = 'all' | 'snoozed' | 'delivered'

const notifications = ref<Notification[]>([])
const loading = ref(true)
const error = ref('')
const mode = ref<ViewMode>('all')

const MODES: { value: ViewMode; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'snoozed', label: 'Snoozed' },
  { value: 'delivered', label: 'Delivered' },
]

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    notifications.value = await listNotifications(50)
  } catch (e) {
    error.value = "Couldn't load your history. Try again in a moment."
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

const visible = computed(() => {
  if (mode.value === 'snoozed') return notifications.value.filter((n) => n.ack_action === 'snoozed')
  if (mode.value === 'delivered') {
    return notifications.value
      .filter((n) => n.delivered_at)
      .slice()
      .sort((a, b) => new Date(b.delivered_at!).getTime() - new Date(a.delivered_at!).getTime())
  }
  return notifications.value
})

function dayLabel(iso: string): string {
  const d = new Date(iso)
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' })
}

/** Grouped by day so a long list has landmarks. */
const groups = computed(() => {
  const out: { label: string; items: Notification[] }[] = []
  for (const n of visible.value) {
    const label = dayLabel(mode.value === 'delivered' ? n.delivered_at! : n.scheduled_for)
    const last = out.at(-1)
    if (last?.label === label) last.items.push(n)
    else out.push({ label, items: [n] })
  }
  return out
})

interface Status {
  label: string
  class: string
}

function status(n: Notification): Status {
  if (n.ack_action === 'dismissed')
    return { label: 'Done', class: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200' }
  if (n.ack_action === 'snoozed')
    return {
      label: `Snoozed ${n.ack_snoozed_minutes} min`,
      class: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
    }
  if (n.status === 'failed') return { label: "Couldn't send", class: 'bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200' }
  if (n.status === 'pending') return { label: 'Waiting', class: 'bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300' }
  if (n.delivered_at) return { label: 'On watch', class: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200' }
  return { label: 'Sent', class: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200' }
}

/** How late the watch confirmed delivery vs. the planned time (dispatch latency + reconnects). */
function delay(n: Notification): string | null {
  if (!n.delivered_at) return null
  const s = Math.round((new Date(n.delivered_at).getTime() - new Date(n.scheduled_for).getTime()) / 1000)
  if (s <= 60) return null
  const m = Math.round(s / 60)
  return `arrived ${m} min late`
}

/**
 * The watch re-arms a snoozed reminder entirely on its own (see ReminderService.md in the
 * firmware fork) - the server is never told, so this is an estimate from acked_at +
 * ack_snoozed_minutes, not something the backend schedules or can confirm.
 */
function retrigger(n: Notification): string | null {
  if (n.ack_action !== 'snoozed' || !n.acked_at || n.ack_snoozed_minutes == null) return null
  const at = new Date(new Date(n.acked_at).getTime() + n.ack_snoozed_minutes * 60_000)
  return `back around ${friendlyDateTime(at.toISOString())}`
}
</script>

<template>
  <div>
    <PageHeader title="History" subtitle="Everything sent to your watch, newest first.">
      <button class="btn btn-ghost" :disabled="loading" @click="refresh"><AppIcon name="refresh" :size="18" /> Refresh</button>
    </PageHeader>

    <div class="mb-6">
      <SegmentedControl v-model="mode" :options="MODES" label="Show" />
    </div>

    <p v-if="error" class="error-box mb-4" role="alert">{{ error }}</p>

    <div v-if="loading" class="space-y-3" aria-busy="true">
      <div v-for="i in 4" :key="i" class="card h-16 animate-pulse" />
    </div>

    <EmptyState
      v-else-if="!visible.length"
      icon="history"
      :title="mode === 'snoozed' ? 'Nothing snoozed' : mode === 'delivered' ? 'Nothing delivered yet' : 'Nothing sent yet'"
      text="Reminders will show up here once they've been sent to your watch."
    />

    <div v-else class="space-y-6">
      <section v-for="g in groups" :key="g.label">
        <h2 class="text-sm font-bold uppercase tracking-wider muted mb-2">{{ g.label }}</h2>
        <ul class="space-y-2">
          <li v-for="n in g.items" :key="n.id" class="card !py-3.5 flex items-start gap-3.5">
            <span class="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-xl" :class="KINDS[n.kind].badge">
              <AppIcon :name="KINDS[n.kind].icon" :size="20" />
            </span>
            <div class="min-w-0 flex-1">
              <div class="flex items-start justify-between gap-3">
                <p class="font-semibold break-words">{{ headline(n).main }}</p>
                <span class="rounded-full px-2.5 py-1 text-xs font-bold shrink-0" :class="status(n).class">{{ status(n).label }}</span>
              </div>
              <p v-if="headline(n).sub" class="text-sm muted whitespace-pre-line line-clamp-3">{{ headline(n).sub }}</p>
              <p class="text-sm muted mt-0.5">
                <span class="tabular-nums">{{ clock(new Date(n.scheduled_for)) }}</span>
                <template v-if="delay(n)"> · {{ delay(n) }}</template>
                <template v-if="retrigger(n)"> · {{ retrigger(n) }}</template>
              </p>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
