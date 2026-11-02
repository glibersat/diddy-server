/** Human-friendly time helpers. Short, plain wording: "in 20 min", "Today 14:30". */

/** Current weekday bit (Mon=0 … Sun=6, matching weekdays_mask) and HH:MM in `timeZone`. */
export function nowIn(timeZone?: string): { weekdayBit: number; hhmm: string } {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone,
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date())
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? ''
  const order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
  return { weekdayBit: order.indexOf(get('weekday')), hhmm: `${get('hour')}:${get('minute')}` }
}

/** "HH:MM:SS" or "HH:MM" from the API → "HH:MM". */
export function shortTime(t: string): string {
  return t.slice(0, 5)
}

export function clock(d: Date): string {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function dayDiff(d: Date, ref = new Date()): number {
  const a = new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const b = new Date(ref.getFullYear(), ref.getMonth(), ref.getDate()).getTime()
  return Math.round((a - b) / 86_400_000)
}

/** "Today 14:30", "Tomorrow 09:00", "Yesterday 18:00", "Mon 3 Nov, 10:15". */
export function friendlyDateTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  const diff = dayDiff(d)
  if (diff === 0) return `Today ${clock(d)}`
  if (diff === 1) return `Tomorrow ${clock(d)}`
  if (diff === -1) return `Yesterday ${clock(d)}`
  return `${d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' })}, ${clock(d)}`
}

/** "in 5 min", "in 2 h 10 min", "3 min ago", "just now". */
export function relative(iso: string, ref = new Date()): string {
  const mins = Math.round((new Date(iso).getTime() - ref.getTime()) / 60_000)
  const abs = Math.abs(mins)
  if (abs < 1) return 'just now'
  let span: string
  if (abs < 60) span = `${abs} min`
  else if (abs < 60 * 24) {
    const h = Math.floor(abs / 60)
    const m = abs % 60
    span = m ? `${h} h ${m} min` : `${h} h`
  } else {
    const days = Math.round(abs / (60 * 24))
    span = `${days} day${days === 1 ? '' : 's'}`
  }
  return mins > 0 ? `in ${span}` : `${span} ago`
}
