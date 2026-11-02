import { createRouter, createWebHistory } from 'vue-router'
import { getApiKey } from './api'
import LoginView from './views/LoginView.vue'
import TodayView from './views/TodayView.vue'
import MoreView from './views/MoreView.vue'
import SchedulesView from './views/SchedulesView.vue'
import IcsSourcesView from './views/IcsSourcesView.vue'
import NotificationsView from './views/NotificationsView.vue'
import SettingsView from './views/SettingsView.vue'

// Map/chart screens pull in Leaflet and Chart.js: load them only when opened.
const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/today' },
    { path: '/login', name: 'login', component: LoginView },
    { path: '/today', name: 'today', component: TodayView, meta: { requiresAuth: true } },
    { path: '/more', name: 'more', component: MoreView, meta: { requiresAuth: true } },
    { path: '/schedules', name: 'schedules', component: SchedulesView, meta: { requiresAuth: true } },
    { path: '/ics-sources', name: 'ics-sources', component: IcsSourcesView, meta: { requiresAuth: true } },
    { path: '/todo-lists', name: 'todo-lists', component: () => import('./views/TodoListsView.vue'), meta: { requiresAuth: true } },
    { path: '/notifications', name: 'notifications', component: NotificationsView, meta: { requiresAuth: true } },
    { path: '/heart-rate', name: 'heart-rate', component: () => import('./views/HeartRateView.vue'), meta: { requiresAuth: true } },
    { path: '/location', name: 'location', component: () => import('./views/LocationView.vue'), meta: { requiresAuth: true } },
    { path: '/settings', name: 'settings', component: SettingsView, meta: { requiresAuth: true } },
  ],
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !getApiKey()) {
    return { name: 'login' }
  }
  return true
})

export default router
