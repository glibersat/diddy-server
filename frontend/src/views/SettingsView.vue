<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { clearApiKey, getApiKey, getMe, updateMe, type User } from '../api'
import AppIcon from '../components/AppIcon.vue'
import PageHeader from '../components/PageHeader.vue'
import ToggleSwitch from '../components/ToggleSwitch.vue'

const router = useRouter()

const user = ref<User | null>(null)
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const saved = ref(false)

const timezone = ref('')
const digestEnabled = ref(false)
const digestTime = ref('08:00')

const timezones: string[] = (Intl as any).supportedValuesOf?.('timeZone') ?? []
const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone

const apiKey = getApiKey() ?? ''
const keyRevealed = ref(false)
const copied = ref(false)

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    user.value = await getMe()
    timezone.value = user.value.timezone
    digestEnabled.value = user.value.digest_enabled
    digestTime.value = user.value.digest_time?.slice(0, 5) ?? '08:00'
  } catch (e) {
    error.value = "Couldn't load your settings. Try again in a moment."
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
    setTimeout(() => (saved.value = false), 2500)
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? "Couldn't save. Try again."
  } finally {
    saving.value = false
  }
}

async function copyKey() {
  await navigator.clipboard.writeText(apiKey)
  copied.value = true
  setTimeout(() => (copied.value = false), 1500)
}

function logout() {
  clearApiKey()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader title="Settings" />

    <div v-if="loading" class="card h-48 animate-pulse" aria-busy="true" />

    <form v-else class="card space-y-6" @submit.prevent="save">
      <h2 class="text-lg font-bold">Reminders</h2>

      <div>
        <label for="timezone" class="field-label">Your timezone</label>
        <input id="timezone" v-model="timezone" required list="tz-list" class="field" autocomplete="off" />
        <datalist id="tz-list">
          <option v-for="tz in timezones" :key="tz" :value="tz" />
        </datalist>
        <p class="field-hint">
          Routines fire at this timezone's local time.
          <button
            v-if="browserTz && browserTz !== timezone"
            type="button"
            class="font-semibold text-indigo-700 dark:text-indigo-300 underline"
            @click="timezone = browserTz"
          >
            Use {{ browserTz }}
          </button>
        </p>
      </div>

      <div class="space-y-2">
        <ToggleSwitch v-model="digestEnabled" label="Morning summary of my appointments" />
        <p class="field-hint !mt-0">One message listing the day's appointments. Only sent on days you have some.</p>
        <div v-if="digestEnabled" class="pt-1">
          <label for="digest_time" class="field-label">Send it at</label>
          <input id="digest_time" v-model="digestTime" type="time" required class="field !w-auto tabular-nums" />
        </div>
      </div>

      <p v-if="error" class="error-box" role="alert">{{ error }}</p>

      <div class="flex items-center gap-3">
        <button type="submit" :disabled="saving" class="btn btn-primary">{{ saving ? 'Saving…' : 'Save' }}</button>
        <span v-if="saved" class="font-semibold text-emerald-700 dark:text-emerald-300 inline-flex items-center gap-1.5" role="status">
          <AppIcon name="check" :size="18" /> Saved
        </span>
      </div>
    </form>

    <section class="card space-y-5">
      <h2 class="text-lg font-bold">Account</h2>
      <div>
        <p class="field-label">Email</p>
        <p>{{ user?.email ?? '—' }}</p>
      </div>
      <div>
        <p class="field-label">API key</p>
        <p class="field-hint !mt-0 mb-2">Paste this into the companion app on your phone. Keep it private.</p>
        <div class="flex flex-wrap items-center gap-2">
          <code class="rounded-lg bg-stone-100 dark:bg-stone-800 px-3 py-2 font-mono text-sm break-all">
            {{ keyRevealed ? apiKey : '•'.repeat(24) }}
          </code>
          <button type="button" class="btn btn-secondary" @click="keyRevealed = !keyRevealed">
            {{ keyRevealed ? 'Hide' : 'Show' }}
          </button>
          <button type="button" class="btn btn-secondary" @click="copyKey">
            <AppIcon v-if="copied" name="check" :size="18" /> {{ copied ? 'Copied' : 'Copy' }}
          </button>
        </div>
      </div>
      <div class="pt-2 border-t border-stone-100 dark:border-stone-800">
        <button type="button" class="btn btn-ghost !px-0" @click="logout"><AppIcon name="logout" :size="18" /> Log out</button>
      </div>
    </section>
  </div>
</template>
