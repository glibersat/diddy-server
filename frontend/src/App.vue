<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from './components/AppIcon.vue'
import { PRIMARY_NAV, SECONDARY_NAV } from './nav'

const route = useRoute()
const showNav = computed(() => route.name !== 'login')
const inSecondary = computed(() => route.path === '/more' || SECONDARY_NAV.some((n) => route.path.startsWith(n.to)))
</script>

<template>
  <div v-if="!showNav">
    <RouterView />
  </div>

  <div v-else class="min-h-screen md:flex">
    <!-- Desktop sidebar -->
    <aside
      class="hidden md:flex md:flex-col md:w-64 md:shrink-0 md:sticky md:top-0 md:h-screen border-r border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 px-4 py-6"
    >
      <RouterLink to="/today" class="flex items-center gap-2.5 px-3 mb-8 no-underline">
        <span class="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white">
          <AppIcon name="bell" :size="20" />
        </span>
        <span class="text-lg font-bold">Diddy</span>
      </RouterLink>

      <nav aria-label="Main" class="flex flex-col gap-1">
        <RouterLink
          v-for="n in PRIMARY_NAV"
          :key="n.to"
          :to="n.to"
          class="flex items-center gap-3 rounded-xl px-3 py-2.5 font-semibold text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800"
          active-class="!bg-indigo-50 !text-indigo-700 dark:!bg-indigo-950 dark:!text-indigo-200"
        >
          <AppIcon :name="n.icon" :size="22" />
          {{ n.label }}
        </RouterLink>
      </nav>

      <p class="mt-8 mb-2 px-3 text-xs font-bold uppercase tracking-wider muted">More</p>
      <nav aria-label="More" class="flex flex-col gap-1">
        <RouterLink
          v-for="n in SECONDARY_NAV"
          :key="n.to"
          :to="n.to"
          class="flex items-center gap-3 rounded-xl px-3 py-2 text-stone-600 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
          active-class="!bg-indigo-50 !text-indigo-700 dark:!bg-indigo-950 dark:!text-indigo-200 font-semibold"
        >
          <AppIcon :name="n.icon" :size="20" />
          {{ n.label }}
        </RouterLink>
      </nav>
    </aside>

    <main class="flex-1 min-w-0 px-5 pt-6 pb-28 md:px-10 md:pt-10 md:pb-12">
      <div class="mx-auto max-w-3xl">
        <RouterView />
      </div>
    </main>

    <!-- Phone bottom bar -->
    <nav
      aria-label="Main"
      class="md:hidden fixed inset-x-0 bottom-0 z-30 border-t border-stone-200 dark:border-stone-800 bg-white/95 dark:bg-stone-900/95 backdrop-blur pb-[env(safe-area-inset-bottom)]"
    >
      <div class="grid grid-cols-5">
        <RouterLink
          v-for="n in PRIMARY_NAV"
          :key="n.to"
          :to="n.to"
          class="flex flex-col items-center gap-0.5 py-2.5 text-xs font-semibold text-stone-500 dark:text-stone-400"
          active-class="!text-indigo-600 dark:!text-indigo-300"
        >
          <AppIcon :name="n.icon" :size="24" />
          {{ n.label }}
        </RouterLink>
        <RouterLink
          to="/more"
          class="flex flex-col items-center gap-0.5 py-2.5 text-xs font-semibold"
          :class="inSecondary ? 'text-indigo-600 dark:text-indigo-300' : 'text-stone-500 dark:text-stone-400'"
        >
          <AppIcon name="more" :size="24" />
          More
        </RouterLink>
      </div>
    </nav>
  </div>
</template>
