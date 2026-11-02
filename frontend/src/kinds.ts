import type { ReminderKind } from './api'
import type { IconName } from './icons'

/** One consistent look per reminder kind, always icon + label + color (never color alone). */
export interface KindMeta {
  label: string
  icon: IconName
  /** Soft badge: background + text. */
  badge: string
  /** Solid accent for the left stripe of a card. */
  stripe: string
}

export const KINDS: Record<ReminderKind, KindMeta> = {
  medication: {
    label: 'Medication',
    icon: 'pill',
    badge: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200',
    stripe: 'bg-emerald-500',
  },
  appointment: {
    label: 'Appointment',
    icon: 'calendar',
    badge: 'bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200',
    stripe: 'bg-sky-500',
  },
  generic: {
    label: 'Other',
    icon: 'bell',
    badge: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200',
    stripe: 'bg-amber-500',
  },
}

export const KIND_ORDER: ReminderKind[] = ['medication', 'appointment', 'generic']

/**
 * What to show as the big line vs. the small line. Daily routines are sent with the generic
 * title "Reminder" and the real text in the body (app/scheduler/daily.py), so lead with the body.
 */
export function headline(n: { title: string; body: string }): { main: string; sub: string | null } {
  if (n.title === 'Reminder' && n.body) return { main: n.body, sub: null }
  return { main: n.title, sub: n.body && n.body !== n.title ? n.body : null }
}
