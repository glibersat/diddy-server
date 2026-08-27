<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getMe, updateMe } from '../api'
import { btnPrimary, card, errorText, input, label, muted } from '../ui'

const loading = ref(true)
const saving = ref(false)
const error = ref('')
const saved = ref(false)

const signalNumber = ref('')

const SIGNAL_NUMBER_PATTERN = /^\+[1-9]\d{6,14}$/

function isValidSignalNumber(value: string): boolean {
  return value === '' || SIGNAL_NUMBER_PATTERN.test(value)
}

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const me = await getMe()
    signalNumber.value = me.signal_number ?? ''
  } catch (e) {
    error.value = 'Could not load your settings'
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

async function save() {
  if (!isValidSignalNumber(signalNumber.value)) {
    error.value = 'Enter a full international number starting with + (e.g. +15551234567)'
    return
  }
  saving.value = true
  error.value = ''
  saved.value = false
  try {
    await updateMe({ signal_number: signalNumber.value || null })
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
    <p :class="[muted, 'mb-4']">Account-wide preferences, not tied to any single reminder.</p>

    <p v-if="loading">Loading…</p>
    <div v-else :class="card">
      <h3 class="font-semibold mb-1">Signal messaging</h3>
      <p :class="[muted, 'mb-3']">
        If set, every notification is also sent to this number as a Signal message, alongside the
        watch trigger. Requires the server operator to have configured a Signal account
        (<code>DIDDY_SIGNAL_ACCOUNT</code>) - ask them if messages aren't arriving.
      </p>
      <form class="space-y-4" @submit.prevent="save">
        <div>
          <label for="signal_number" :class="label">Your Signal number</label>
          <input
            id="signal_number"
            v-model="signalNumber"
            placeholder="+15551234567"
            :class="[input, 'w-full']"
          />
        </div>
        <p v-if="error" :class="errorText">{{ error }}</p>
        <div class="flex items-center gap-3">
          <button type="submit" :disabled="saving" :class="btnPrimary">
            {{ saving ? 'Saving…' : 'Save' }}
          </button>
          <span v-if="saved" class="text-sm text-green-600 dark:text-green-400">Saved</span>
        </div>
      </form>
    </div>
  </div>
</template>
