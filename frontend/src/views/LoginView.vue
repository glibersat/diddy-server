<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { createUser, getMe, setApiKey } from '../api'

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
    router.push({ name: 'schedules' })
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? 'Could not create account'
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
    router.push({ name: 'schedules' })
  } catch (e: any) {
    error.value = 'That API key was not recognized'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="max-w-md mx-auto mt-12">
    <h1 class="text-lg font-semibold">Diddy Reminders</h1>
    <p class="text-sm text-neutral-500 dark:text-neutral-400">
      Configure your daily watch reminders and ICS calendar feed.
    </p>

    <div
      class="bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-xl p-5 mt-4"
    >
      <div class="flex gap-2 mb-5">
        <button
          class="rounded-md px-4 py-2 cursor-pointer"
          :class="
            mode === 'create'
              ? 'bg-indigo-600 text-white'
              : 'bg-transparent border border-neutral-300 dark:border-neutral-700 text-neutral-900 dark:text-neutral-100'
          "
          @click="mode = 'create'"
        >
          New account
        </button>
        <button
          class="rounded-md px-4 py-2 cursor-pointer"
          :class="
            mode === 'existing'
              ? 'bg-indigo-600 text-white'
              : 'bg-transparent border border-neutral-300 dark:border-neutral-700 text-neutral-900 dark:text-neutral-100'
          "
          @click="mode = 'existing'"
        >
          I have an API key
        </button>
      </div>

      <form v-if="mode === 'create'" class="space-y-4" @submit.prevent="handleCreate">
        <div>
          <label for="email" class="block text-sm text-neutral-500 dark:text-neutral-400 mb-1">Email</label>
          <input
            id="email"
            v-model="email"
            type="email"
            required
            placeholder="you@example.com"
            class="w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2"
          />
        </div>
        <div>
          <label for="tz" class="block text-sm text-neutral-500 dark:text-neutral-400 mb-1">Timezone</label>
          <input
            id="tz"
            v-model="timezone"
            required
            class="w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2"
          />
        </div>
        <p v-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
        <button
          type="submit"
          :disabled="loading"
          class="rounded-md px-4 py-2 bg-indigo-600 text-white disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ loading ? 'Creating…' : 'Create account' }}
        </button>
      </form>

      <form v-else class="space-y-4" @submit.prevent="handleExisting">
        <div>
          <label for="key" class="block text-sm text-neutral-500 dark:text-neutral-400 mb-1">API key</label>
          <input
            id="key"
            v-model="apiKeyInput"
            required
            placeholder="paste your api key"
            class="w-full rounded-md border border-neutral-300 dark:border-neutral-700 bg-white dark:bg-neutral-900 px-3 py-2"
          />
        </div>
        <p v-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>
        <button
          type="submit"
          :disabled="loading"
          class="rounded-md px-4 py-2 bg-indigo-600 text-white disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ loading ? 'Checking…' : 'Continue' }}
        </button>
      </form>
    </div>
  </div>
</template>
