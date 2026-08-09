import { createRouter, createWebHistory } from 'vue-router'
import { getApiKey } from './api'
import LoginView from './views/LoginView.vue'
import SchedulesView from './views/SchedulesView.vue'
import IcsSourcesView from './views/IcsSourcesView.vue'
import NotificationsView from './views/NotificationsView.vue'
import HeartRateView from './views/HeartRateView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/schedules' },
    { path: '/login', name: 'login', component: LoginView },
    { path: '/schedules', name: 'schedules', component: SchedulesView, meta: { requiresAuth: true } },
    { path: '/ics-sources', name: 'ics-sources', component: IcsSourcesView, meta: { requiresAuth: true } },
    { path: '/notifications', name: 'notifications', component: NotificationsView, meta: { requiresAuth: true } },
    { path: '/heart-rate', name: 'heart-rate', component: HeartRateView, meta: { requiresAuth: true } },
  ],
})

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !getApiKey()) {
    return { name: 'login' }
  }
  return true
})

export default router
