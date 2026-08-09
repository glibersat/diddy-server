<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { listNotifications, type Notification } from '../api'
import { card, muted } from '../ui'

const notifications = ref<Notification[]>([])
const loading = ref(true)
const error = ref('')
const snoozedOnly = ref(true)

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    notifications.value = await listNotifications()
  } catch (e) {
    error.value = 'Could not load notifications'
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

const visible = computed(() =>
  snoozedOnly.value ? notifications.value.filter((n) => n.ack_action === 'snoozed') : notifications.value,
)

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
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
      <label class="flex items-center gap-1.5 text-sm">
        <input type="checkbox" v-model="snoozedOnly" class="w-auto inline-block align-middle" />
        Snoozed only
      </label>
    </div>
    <p :class="[muted, 'mb-4']">Outbox of everything sent to the watch, most recent first.</p>

    <p v-if="loading">Loading…</p>
    <p v-else-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
    <p v-else-if="!visible.length" :class="muted">
      {{ snoozedOnly ? 'No snoozed notifications.' : 'No notifications yet.' }}
    </p>

    <div v-for="n in visible" :key="n.id" :class="[card, 'flex justify-between items-start flex-wrap gap-3']">
      <div>
        <div class="font-medium">{{ n.title }}</div>
        <div :class="[muted, 'whitespace-pre-line']">{{ n.body }}</div>
        <div :class="[muted, 'mt-1']">
          Scheduled {{ formatDateTime(n.scheduled_for) }} · {{ n.kind }}
          <span v-if="n.ack_action === 'snoozed'">
            · snoozed {{ n.ack_snoozed_minutes }}m at {{ formatDateTime(n.acked_at) }} · re-fires on-watch at
            {{ formatRetrigger(n) }}
          </span>
          <span v-else-if="n.ack_action === 'dismissed'"> · dismissed at {{ formatDateTime(n.acked_at) }}</span>
          <span v-else> · {{ n.status }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
