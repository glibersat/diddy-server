<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { clearApiKey, getApiKey, ringPhone } from './api'

const route = useRoute()
const router = useRouter()
const loggedIn = ref(!!getApiKey())
const apiKey = computed(() => getApiKey() ?? '')
const keyRevealed = ref(false)
const copied = ref(false)
const ringStatus = ref<'idle' | 'ringing' | 'unreachable'>('idle')

const showNav = computed(() => route.name !== 'login')

function logout() {
  clearApiKey()
  loggedIn.value = false
  router.push({ name: 'login' })
}

async function ring() {
  ringStatus.value = 'ringing'
  try {
    const delivered = await ringPhone()
    ringStatus.value = delivered ? 'ringing' : 'unreachable'
  } catch (e) {
    ringStatus.value = 'unreachable'
  } finally {
    setTimeout(() => (ringStatus.value = 'idle'), 2000)
  }
}

async function copyKey() {
  await navigator.clipboard.writeText(apiKey.value)
  copied.value = true
  setTimeout(() => (copied.value = false), 1500)
}
</script>

<template>
  <div class="max-w-3xl mx-auto p-6">
    <header
      v-if="showNav"
      class="mb-8 pb-4 border-b border-neutral-200 dark:border-neutral-800"
    >
      <div class="flex items-center gap-6">
        <h1 class="text-lg font-semibold m-0">Diddy Reminders</h1>
        <nav class="flex gap-4 flex-1">
          <RouterLink
            to="/schedules"
            class="py-1 text-neutral-500 dark:text-neutral-400 no-underline border-b-2 border-transparent"
            active-class="!text-neutral-900 dark:!text-neutral-100 !border-indigo-500"
          >
            Daily Reminders
          </RouterLink>
          <RouterLink
            to="/ics-sources"
            class="py-1 text-neutral-500 dark:text-neutral-400 no-underline border-b-2 border-transparent"
            active-class="!text-neutral-900 dark:!text-neutral-100 !border-indigo-500"
          >
            ICS Sources
          </RouterLink>
          <RouterLink
            to="/notifications"
            class="py-1 text-neutral-500 dark:text-neutral-400 no-underline border-b-2 border-transparent"
            active-class="!text-neutral-900 dark:!text-neutral-100 !border-indigo-500"
          >
            Notifications
          </RouterLink>
          <RouterLink
            to="/heart-rate"
            class="py-1 text-neutral-500 dark:text-neutral-400 no-underline border-b-2 border-transparent"
            active-class="!text-neutral-900 dark:!text-neutral-100 !border-indigo-500"
          >
            Heart Rate
          </RouterLink>
        </nav>
        <button
          type="button"
          class="bg-transparent border border-neutral-300 dark:border-neutral-700 text-neutral-900 dark:text-neutral-100 rounded-md px-4 py-2 cursor-pointer disabled:opacity-60"
          :disabled="ringStatus === 'ringing'"
          @click="ring"
        >
          {{ ringStatus === 'ringing' ? 'Ringing…' : ringStatus === 'unreachable' ? 'Phone unreachable' : 'Ring phone' }}
        </button>
        <button
          class="bg-transparent border border-neutral-300 dark:border-neutral-700 text-neutral-900 dark:text-neutral-100 rounded-md px-4 py-2 cursor-pointer"
          @click="logout"
        >
          Log out
        </button>
      </div>

      <div class="flex items-center gap-2 mt-3 text-sm text-neutral-500 dark:text-neutral-400">
        <span>API key:</span>
        <code class="font-mono">{{ keyRevealed ? apiKey : '•'.repeat(24) }}</code>
        <button
          type="button"
          class="bg-transparent border border-neutral-300 dark:border-neutral-700 text-neutral-900 dark:text-neutral-100 rounded-md px-2 py-0.5 text-xs cursor-pointer"
          @click="keyRevealed = !keyRevealed"
        >
          {{ keyRevealed ? 'Hide' : 'Show' }}
        </button>
        <button
          type="button"
          class="bg-transparent border border-neutral-300 dark:border-neutral-700 text-neutral-900 dark:text-neutral-100 rounded-md px-2 py-0.5 text-xs cursor-pointer"
          @click="copyKey"
        >
          {{ copied ? 'Copied!' : 'Copy' }}
        </button>
      </div>
    </header>
    <main>
      <RouterView />
    </main>
  </div>
</template>
