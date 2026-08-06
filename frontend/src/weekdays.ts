export const WEEKDAYS = [
  { bit: 0, label: 'Mon' },
  { bit: 1, label: 'Tue' },
  { bit: 2, label: 'Wed' },
  { bit: 3, label: 'Thu' },
  { bit: 4, label: 'Fri' },
  { bit: 5, label: 'Sat' },
  { bit: 6, label: 'Sun' },
]

export function maskHasDay(mask: number, bit: number): boolean {
  return (mask & (1 << bit)) !== 0
}

export function toggleDay(mask: number, bit: number): number {
  return mask ^ (1 << bit)
}

export function describeMask(mask: number): string {
  if (mask === 0b1111111) return 'Every day'
  if (mask === 0b0011111) return 'Weekdays'
  if (mask === 0b1100000) return 'Weekends'
  const days = WEEKDAYS.filter((d) => maskHasDay(mask, d.bit)).map((d) => d.label)
  return days.length ? days.join(', ') : 'Never'
}
