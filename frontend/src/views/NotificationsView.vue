<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getNextNotification, listNotifications, type NextReminder, type Notification } from '../api'
import { card, muted } from '../ui'

type ViewMode = 'snoozed' | 'delivered' | 'all'

const notifications = ref<Notification[]>([])
const nextUp = ref<NextReminder | null>(null)
const loading = ref(true)
const error = ref('')
const mode = ref<ViewMode>('snoozed')

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const [notifs, next] = await Promise.all([listNotifications(), getNextNotification()])
    notifications.value = notifs
    nextUp.value = next
  } catch (e) {
    error.value = 'Could not load notifications'
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

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

/** How late (or, in principle, early) a `delivered` confirmation landed vs. when the reminder was
 * scheduled to fire - the gap covers dispatch latency plus any time spent waiting for the watch
 * to reconnect. */
function formatDelay(scheduledFor: string, deliveredAt: string): string {
  const deltaSeconds = Math.round((new Date(deliveredAt).getTime() - new Date(scheduledFor).getTime()) / 1000)
  if (deltaSeconds <= 1) return 'on time'
  const minutes = Math.floor(deltaSeconds / 60)
  const seconds = deltaSeconds % 60
  return minutes > 0 ? `+${minutes}m ${seconds}s` : `+${seconds}s`
}

/**
 * The watch re-arms a snoozed reminder entirely on its own (see ReminderService.md in the
 * firmware fork) - the server is never told, so this is a computed estimate from acked_at +
 * ack_snoozed_minutes, not something the backend actually schedules or can confirm happened.
 */
function formatRetrigger(n: Notification): string {
  if (!n.acked_at || n.ack_snoozed_minutes == null) return '—'
  const at = new Date(n.acked_at)
  at.setMinutes(at.getMinutes() + n.ack_snoozed_minutes)
  return at.toLocaleString()
}
</script>

<template>
  <div>
    <div class="flex justify-between items-center">
      <h2 class="text-base font-semibold">Notifications</h2>
      <select v-model="mode" class="text-sm w-auto">
        <option value="snoozed">Snoozed</option>
        <option value="delivered">Delivered</option>
        <option value="all">All</option>
      </select>
    </div>
    <p :class="[muted, 'mb-4']">Outbox of everything sent to the watch, most recent first.</p>

    <p v-if="loading">Loading…</p>
    <p v-else-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    <p v-else-if="!visible.length" :class="muted">
      {{ mode === 'snoozed' ? 'No snoozed notifications.' : mode === 'delivered' ? 'Nothing delivered yet.' : 'No notifications yet.' }}
    </p>

    <div v-for="n in visible" :key="n.id" :class="[card, 'flex justify-between items-start flex-wrap gap-3']">
      <div>
        <div class="font-medium">{{ n.title }}</div>
        <div :class="[muted, 'whitespace-pre-line']">{{ n.body }}</div>
        <div :class="[muted, 'mt-1']">
          Scheduled {{ formatDateTime(n.scheduled_for) }} · {{ n.kind }}
          <span v-if="mode === 'delivered' && n.delivered_at">
            · delivered at {{ formatDateTime(n.delivered_at) }} ({{ formatDelay(n.scheduled_for, n.delivered_at) }})
          </span>
          <span v-else-if="n.ack_action === 'snoozed'">
            · snoozed {{ n.ack_snoozed_minutes }}m at {{ formatDateTime(n.acked_at) }} · re-fires on-watch at
            {{ formatRetrigger(n) }}
          </span>
          <span v-else-if="n.ack_action === 'dismissed'"> · dismissed at {{ formatDateTime(n.acked_at) }}</span>
          <span v-else> · {{ n.status }}</span>
        </div>
      </div>
    </div>

    <div v-if="mode === 'snoozed' && !loading && nextUp" :class="[card, 'border-dashed']">
      <div :class="[muted, 'text-xs uppercase tracking-wide mb-1']">Next up</div>
      <div class="font-medium">{{ nextUp.title }}</div>
      <div :class="[muted, 'whitespace-pre-line']">{{ nextUp.body }}</div>
      <div :class="[muted, 'mt-1']">Expected {{ formatDateTime(nextUp.scheduled_for) }} · {{ nextUp.kind }}</div>
    </div>
  </div>
</template>
