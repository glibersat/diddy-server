import type { IconName } from './icons'

export interface NavItem {
  to: string
  label: string
  icon: IconName
  /** One-line plain-language explanation, shown on the "More" page. */
  hint: string
}

/** The everyday screens: always one tap away (sidebar on desktop, bottom bar on phones). */
export const PRIMARY_NAV: NavItem[] = [
  { to: '/today', label: 'Today', icon: 'home', hint: "What's next and what's left today" },
  { to: '/schedules', label: 'Routines', icon: 'repeat', hint: 'Reminders at the same time every day' },
  { to: '/ics-sources', label: 'Calendars', icon: 'calendar', hint: 'Heads-ups before your calendar events' },
  { to: '/todo-lists', label: 'Lists', icon: 'list', hint: 'Todo lists, optionally tied to a place' },
]

/** Occasional screens: grouped away so they don't compete for attention. */
export const SECONDARY_NAV: NavItem[] = [
  { to: '/notifications', label: 'History', icon: 'history', hint: 'Everything sent to your watch' },
  { to: '/heart-rate', label: 'Heart rate', icon: 'heart', hint: 'Readings from your watch' },
  { to: '/location', label: 'Find my phone', icon: 'phone', hint: 'Where your phone was last seen, and ring it' },
  { to: '/settings', label: 'Settings', icon: 'settings', hint: 'Timezone, morning summary, account' },
]
