<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { apiDetail, clearApiKey, connectionProblem, createUser, getMe, serverLabel, setApiKey } from '../api'
import AppIcon from '../components/AppIcon.vue'
import SegmentedControl from '../components/SegmentedControl.vue'

const router = useRouter()
const mode = ref<'create' | 'existing'>('create')

const email = ref('')
const timezone = ref(Intl.DateTimeFormat().resolvedOptions().timeZone ?? 'UTC')
const apiKeyInput = ref('')

const loading = ref(false)
const error = ref('')

async function handleCreate() {
  error.value = ''
  loading.value = true
  try {
    const user = await createUser(email.value, timezone.value)
    setApiKey(user.api_key)
    router.push({ name: 'today' })
  } catch (e) {
    error.value = connectionProblem(e) ?? apiDetail(e) ?? "Couldn't create your account. Try again."
  } finally {
    loading.value = false
  }
}

async function handleExisting() {
  error.value = ''
  loading.value = true
  try {
    setApiKey(apiKeyInput.value.trim())
    await getMe()
    router.push({ name: 'today' })
  } catch (e) {
    // Never keep an unverified key: the router would let us in and every screen would fail.
    // The key stays in the input, so retrying is one tap.
    clearApiKey()
    const status = axios.isAxiosError(e) ? e.response?.status : undefined
    if (status === 401 || status === 403) {
      error.value = `The server at ${serverLabel()} didn't recognise that key. Check it and try again.`
    } else {
      const problem = connectionProblem(e) ?? "Couldn't check your key. Try again."
      error.value = `${problem} Your key is still in the box.`
    }
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center px-5 py-10">
    <div class="w-full max-w-md">
      <div class="flex items-center gap-3 mb-6">
        <span class="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-600 text-white">
          <AppIcon name="bell" :size="26" />
        </span>
        <div>
          <h1 class="text-2xl font-bold">Diddy</h1>
          <p class="muted">Gentle reminders on your watch.</p>
        </div>
      </div>

      <div class="card space-y-5">
        <SegmentedControl
          v-model="mode"
          label="Account"
          :options="[
            { value: 'create', label: 'New here' },
            { value: 'existing', label: 'I have a key' },
          ]"
        />

        <form v-if="mode === 'create'" class="space-y-5" @submit.prevent="handleCreate">
          <div>
            <label for="email" class="field-label">Email</label>
            <input id="email" v-model="email" type="email" required autocomplete="email" placeholder="you@example.com" class="field" />
          </div>
          <div>
            <label for="tz" class="field-label">Timezone</label>
            <input id="tz" v-model="timezone" required class="field" />
            <p class="field-hint">We guessed this from your browser. It's usually right.</p>
          </div>
          <p v-if="error" class="error-box" role="alert">{{ error }}</p>
          <button type="submit" :disabled="loading" class="btn btn-primary w-full">
            {{ loading ? 'Creating…' : 'Create my account' }}
          </button>
        </form>

        <form v-else class="space-y-5" @submit.prevent="handleExisting">
          <div>
            <label for="key" class="field-label">Your API key</label>
            <input id="key" v-model="apiKeyInput" required placeholder="Paste it here" class="field font-mono" />
          </div>
          <p v-if="error" class="error-box" role="alert">{{ error }}</p>
          <button type="submit" :disabled="loading" class="btn btn-primary w-full">
            {{ loading ? 'Checking…' : 'Continue' }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
