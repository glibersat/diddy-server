<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getMe, updateMe, type User } from '../api'
import { btnPrimary, card, errorText, input, label, muted } from '../ui'

const user = ref<User | null>(null)
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const saved = ref(false)

const timezone = ref('')
const digestEnabled = ref(false)
const digestTime = ref('08:00')

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    user.value = await getMe()
    timezone.value = user.value.timezone
    digestEnabled.value = user.value.digest_enabled
    digestTime.value = user.value.digest_time ?? '08:00'
  } catch (e) {
    error.value = 'Could not load your account'
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

async function save() {
  saving.value = true
  saved.value = false
  error.value = ''
  try {
    user.value = await updateMe({
      timezone: timezone.value,
      digest_enabled: digestEnabled.value,
      digest_time: digestEnabled.value ? digestTime.value : null,
    })
    saved.value = true
    setTimeout(() => (saved.value = false), 2000)
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? 'Could not save settings'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div>
    <h2 class="text-base font-semibold">Settings</h2>
    <p :class="[muted, 'mb-4']">Your account and notification preferences.</p>

    <p v-if="loading">Loading…</p>

    <form v-else :class="card" class="space-y-4" @submit.prevent="save">
      <div>
        <label for="email" :class="label">Email</label>
        <p id="email">{{ user?.email }}</p>
      </div>

      <div>
        <label for="timezone" :class="label">Timezone</label>
        <input id="timezone" v-model="timezone" required :class="[input, 'w-full']" />
      </div>

      <div>
        <label :class="label">
          <input type="checkbox" v-model="digestEnabled" class="w-auto inline-block mr-1.5 align-middle" />
          Send a daily schedule digest
        </label>
        <p :class="[muted, 'mb-2']">
          A once-a-day summary of the day's appointments, sent at the time below (your local
          timezone) - only on days you have at least one appointment.
        </p>
        <input
          v-if="digestEnabled"
          id="digest_time"
          v-model="digestTime"
          type="time"
          required
          :class="input"
        />
      </div>

      <p v-if="error" :class="errorText">{{ error }}</p>

      <button type="submit" :disabled="saving" :class="btnPrimary">
        {{ saving ? 'Saving…' : saved ? 'Saved!' : 'Save' }}
      </button>
    </form>
  </div>
</template>
