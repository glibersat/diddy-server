<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  getMe,
  getNextNotification,
  listNotifications,
  listSchedules,
  ringPhone,
  sendAlert,
  type DailySchedule,
  type NextReminder,
  type Notification,
} from '../api'
import AppIcon from '../components/AppIcon.vue'
import EmptyState from '../components/EmptyState.vue'
import { KINDS, headline } from '../kinds'
import { clock, nowIn, relative, shortTime } from '../time'
import { maskHasDay } from '../weekdays'

const loading = ref(true)
const error = ref('')
const timezone = ref<string | undefined>(undefined)
const schedules = ref<DailySchedule[]>([])
const notifications = ref<Notification[]>([])
const nextUp = ref<NextReminder | null>(null)
const now = ref(new Date())

async function refresh() {
  error.value = ''
  try {
    const [me, scheds, notifs, next] = await Promise.all([
      getMe(),
      listSchedules(),
      listNotifications(100),
      getNextNotification(),
    ])
    timezone.value = me.timezone
    schedules.value = scheds
    notifications.value = notifs
    nextUp.value = next
  } catch (e) {
    error.value = "Couldn't load today. Check your connection and try again."
  } finally {
    loading.value = false
  }
}

let tick: ReturnType<typeof setInterval> | undefined
let poll: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  refresh()
  tick = setInterval(() => (now.value = new Date()), 30_000)
  poll = setInterval(refresh, 120_000)
})
onBeforeUnmount(() => {
  clearInterval(tick)
  clearInterval(poll)
})

/** YYYY-MM-DD in the user's timezone, to compare "is this today?" the way the server does. */
function dayKey(d: Date): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: timezone.value }).format(d)
}

const today = computed(() => {
  // Recompute when `now` ticks.
  void now.value
  return nowIn(timezone.value)
})

const todayLabel = computed(() =>
  now.value.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long', timeZone: timezone.value }),
)

type RowState = 'done' | 'snoozed' | 'sent' | 'upcoming' | 'missed'

interface Row {
  schedule: DailySchedule
  time: string
  state: RowState
}

const rows = computed<Row[]>(() => {
  const key = dayKey(now.value)
  return schedules.value
    .filter((s) => s.enabled && maskHasDay(s.weekdays_mask, today.value.weekdayBit))
    .map((s) => {
      const time = shortTime(s.time_of_day)
      const n = notifications.value.find(
        (n) => n.rule_type === 'daily_schedule' && n.rule_id === s.id && dayKey(new Date(n.scheduled_for)) === key,
      )
      let state: RowState
      if (n?.ack_action === 'dismissed') state = 'done'
      else if (n?.ack_action === 'snoozed') state = 'snoozed'
      else if (n?.status === 'failed') state = 'missed'
      else if (n) state = 'sent'
      else state = time > today.value.hhmm ? 'upcoming' : 'missed'
      return { schedule: s, time, state }
    })
    .sort((a, b) => a.time.localeCompare(b.time))
})

const doneCount = computed(() => rows.value.filter((r) => r.state === 'done').length)
const progress = computed(() => (rows.value.length ? Math.round((doneCount.value / rows.value.length) * 100) : 0))

/** Snoozed reminders whose watch re-fire is still ahead. Estimated - the watch re-arms on its own. */
const snoozed = computed(() =>
  notifications.value
    .filter((n) => n.ack_action === 'snoozed' && n.acked_at && n.ack_snoozed_minutes != null)
    .map((n) => ({ n, at: new Date(new Date(n.acked_at!).getTime() + n.ack_snoozed_minutes! * 60_000) }))
    .filter(({ at }) => at > now.value)
    .sort((a, b) => a.at.getTime() - b.at.getTime()),
)

const STATE_META: Record<RowState, { label: string; class: string }> = {
  done: { label: 'Done', class: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200' },
  snoozed: { label: 'Snoozed', class: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200' },
  sent: { label: 'On your watch', class: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200' },
  upcoming: { label: 'Later', class: 'bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300' },
  missed: { label: 'Not sent', class: 'bg-stone-100 text-stone-500 dark:bg-stone-800 dark:text-stone-400' },
}

type QuickState = 'idle' | 'busy' | 'ok' | 'fail'
const quickState = reactive<{ ring: QuickState; test: QuickState }>({ ring: 'idle', test: 'idle' })

async function quick(which: 'ring' | 'test', action: () => Promise<boolean>) {
  quickState[which] = 'busy'
  try {
    quickState[which] = (await action()) ? 'ok' : 'fail'
  } catch {
    quickState[which] = 'fail'
  }
  setTimeout(() => (quickState[which] = 'idle'), 3000)
}
</script>

<template>
  <div class="space-y-8">
    <header>
      <p class="muted font-semibold">{{ todayLabel }}</p>
      <h1 class="text-3xl md:text-4xl font-bold tracking-tight">Today</h1>
    </header>

    <p v-if="error" class="error-box" role="alert">{{ error }}</p>

    <div v-if="loading" class="space-y-4" aria-busy="true">
      <div class="card h-36 animate-pulse" />
      <div class="card h-48 animate-pulse" />
    </div>

    <template v-else>
      <!-- 1. The single most important thing: what's next -->
      <section aria-labelledby="next-heading">
        <h2 id="next-heading" class="sr-only">Next up</h2>
        <div
          v-if="nextUp"
          class="relative overflow-hidden rounded-3xl bg-indigo-600 text-white p-6 md:p-8 shadow-lg shadow-indigo-600/20"
        >
          <p class="text-sm font-bold uppercase tracking-wider text-indigo-100">Next up · {{ relative(nextUp.scheduled_for, now) }}</p>
          <div class="mt-3 flex items-start gap-4">
            <span class="mt-1 flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-white/15">
              <AppIcon :name="KINDS[nextUp.kind].icon" :size="26" />
            </span>
            <div class="min-w-0">
              <p class="text-2xl md:text-3xl font-bold leading-tight break-words">{{ headline(nextUp).main }}</p>
              <p v-if="headline(nextUp).sub" class="mt-1 text-indigo-100 whitespace-pre-line">{{ headline(nextUp).sub }}</p>
              <p class="mt-3 text-lg font-semibold tabular-nums">{{ clock(new Date(nextUp.scheduled_for)) }}</p>
            </div>
          </div>
        </div>
        <div v-else class="card flex items-center gap-4">
          <span class="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
            <AppIcon name="check" :size="26" />
          </span>
          <div>
            <p class="text-lg font-semibold">Nothing coming up</p>
            <p class="muted">No reminders planned in the next few hours.</p>
          </div>
        </div>
      </section>

      <!-- 2. Snoozed: things you've pushed back -->
      <section v-if="snoozed.length" aria-labelledby="snoozed-heading">
        <h2 id="snoozed-heading" class="text-lg font-bold mb-3 flex items-center gap-2">
          <AppIcon name="snooze" /> Snoozed
        </h2>
        <ul class="space-y-2">
          <li v-for="{ n, at } in snoozed" :key="n.id" class="card !py-3 flex items-center justify-between gap-3">
            <span class="font-medium min-w-0 truncate">{{ headline(n).main }}</span>
            <span class="text-sm muted shrink-0 tabular-nums">back {{ relative(at.toISOString(), now) }}</span>
          </li>
        </ul>
      </section>

      <!-- 3. Today's routines as a checklist with progress -->
      <section aria-labelledby="routines-heading">
        <div class="flex items-end justify-between gap-3 mb-3">
          <h2 id="routines-heading" class="text-lg font-bold">Today's routines</h2>
          <RouterLink to="/schedules" class="text-sm font-semibold text-indigo-600 dark:text-indigo-300">Edit</RouterLink>
        </div>

        <EmptyState
          v-if="!rows.length"
          icon="repeat"
          title="No routines today"
          text="Routines are reminders that come back at the same time, like taking your meds."
        >
          <RouterLink to="/schedules" class="btn btn-primary"><AppIcon name="plus" /> Add a routine</RouterLink>
        </EmptyState>

        <template v-else>
          <div class="mb-4">
            <div class="flex justify-between text-sm font-semibold mb-1.5">
              <span>{{ doneCount }} of {{ rows.length }} done</span>
              <span v-if="doneCount === rows.length" class="text-emerald-700 dark:text-emerald-300">All done, nice work!</span>
            </div>
            <div class="h-2.5 rounded-full bg-stone-200 dark:bg-stone-800 overflow-hidden" role="progressbar" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100">
              <div class="h-full rounded-full bg-emerald-500 transition-all duration-500" :style="{ width: `${progress}%` }" />
            </div>
          </div>

          <ol class="space-y-2">
            <li
              v-for="r in rows"
              :key="r.schedule.id"
              class="card !p-0 flex items-stretch overflow-hidden"
              :class="{ 'opacity-60': r.state === 'done' || r.state === 'missed' }"
            >
              <span class="w-1.5 shrink-0" :class="KINDS[r.schedule.kind].stripe" aria-hidden="true" />
              <div class="flex flex-1 items-center gap-4 px-4 py-3 min-w-0">
                <span class="tabular-nums text-lg font-bold w-14 shrink-0">{{ r.time }}</span>
                <span class="flex-1 min-w-0">
                  <span class="block font-semibold break-words" :class="{ 'line-through': r.state === 'done' }">
                    {{ r.schedule.message }}
                  </span>
                  <span class="text-sm muted inline-flex items-center gap-1">
                    <AppIcon :name="KINDS[r.schedule.kind].icon" :size="14" /> {{ KINDS[r.schedule.kind].label }}
                  </span>
                </span>
                <span class="rounded-full px-2.5 py-1 text-xs font-bold shrink-0 inline-flex items-center gap-1" :class="STATE_META[r.state].class">
                  <AppIcon v-if="r.state === 'done'" name="check" :size="14" />
                  {{ STATE_META[r.state].label }}
                </span>
              </div>
            </li>
          </ol>
        </template>
      </section>

      <!-- 4. Quick actions -->
      <section aria-labelledby="quick-heading">
        <h2 id="quick-heading" class="text-lg font-bold mb-3">Quick actions</h2>
        <div class="grid grid-cols-2 gap-3">
          <button
            type="button"
            class="card flex flex-col items-start gap-2 text-left hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors disabled:opacity-60"
            :disabled="quickState.ring === 'busy'"
            @click="quick('ring', ringPhone)"
          >
            <AppIcon name="phone" :size="26" class="text-indigo-600 dark:text-indigo-300" />
            <span class="font-semibold">
              {{ quickState.ring === 'busy' ? 'Ringing…' : quickState.ring === 'ok' ? 'Ringing!' : quickState.ring === 'fail' ? "Phone isn't connected" : 'Ring my phone' }}
            </span>
          </button>
          <button
            type="button"
            class="card flex flex-col items-start gap-2 text-left hover:border-indigo-300 dark:hover:border-indigo-700 transition-colors disabled:opacity-60"
            :disabled="quickState.test === 'busy'"
            @click="quick('test', () => sendAlert('Test from Diddy'))"
          >
            <AppIcon name="zap" :size="26" class="text-indigo-600 dark:text-indigo-300" />
            <span class="font-semibold">
              {{ quickState.test === 'busy' ? 'Sending…' : quickState.test === 'ok' ? 'Sent, check your watch' : quickState.test === 'fail' ? "Phone isn't connected" : 'Test my watch' }}
            </span>
          </button>
        </div>
      </section>
    </template>
  </div>
</template>
