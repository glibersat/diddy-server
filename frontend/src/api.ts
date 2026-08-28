import axios from 'axios'

export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

const API_KEY_STORAGE = 'diddy_api_key'

export function getApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE)
}

export function setApiKey(key: string) {
  localStorage.setItem(API_KEY_STORAGE, key)
}

export function clearApiKey() {
  localStorage.removeItem(API_KEY_STORAGE)
}

export const client = axios.create({ baseURL: API_BASE })

client.interceptors.request.use((config) => {
  const key = getApiKey()
  if (key) {
    config.headers['X-API-Key'] = key
  }
  return config
})

export type ReminderKind = 'generic' | 'medication' | 'appointment'

export interface User {
  id: string
  email: string
  api_key: string
  timezone: string
  digest_enabled: boolean
  digest_time: string | null
}

export interface UserUpdateInput {
  timezone?: string
  digest_enabled?: boolean
  digest_time?: string | null
}

export interface DailySchedule {
  id: string
  time_of_day: string
  weekdays_mask: number
  message: string
  enabled: boolean
  kind: ReminderKind
  dismissible: boolean
  snooze_minutes: number[]
}

export type DailyScheduleInput = Omit<DailySchedule, 'id'>

export interface IcsSource {
  id: string
  url_or_path: string
  offsets_minutes: number[]
  refresh_minutes: number
  enabled: boolean
  last_synced_at: string | null
  kind: ReminderKind
  dismissible: boolean
  snooze_minutes: number[]
}

export type IcsSourceInput = Omit<IcsSource, 'id' | 'last_synced_at'>

export interface TodoList {
  id: string
  name: string
  caldav_url: string
  username: string | null
  refresh_minutes: number
  enabled: boolean
  last_synced_at: string | null
  place_label: string | null
  place_latitude: number | null
  place_longitude: number | null
  place_radius_m: number | null
  kind: ReminderKind
  dismissible: boolean
  snooze_minutes: number[]
}

/** `password` is write-only - TodoList (the API response) never includes it back, see
 * app/schemas.py::TodoListOut. */
export interface TodoListInput {
  name: string
  caldav_url: string
  username: string
  password: string
  refresh_minutes: number
  enabled: boolean
  place_label: string | null
  place_latitude: number | null
  place_longitude: number | null
  place_radius_m: number | null
  kind: ReminderKind
  dismissible: boolean
  snooze_minutes: number[]
}

export interface TodoItem {
  id: string
  uid: string
  summary: string
  due: string | null
  completed: boolean
}

export type NotificationStatus = 'pending' | 'sent' | 'acked' | 'failed'
export type AckAction = 'snoozed' | 'dismissed'
/** Which BLE service delivers this notification: `reminder` (dismissible/snoozable, needs an
 * on-watch ack) or `alert` (one-shot, no dismiss/snooze, no ack step). */
export type NotificationChannel = 'reminder' | 'alert'

export type RuleType = 'daily_schedule' | 'ics_reminder' | 'manual' | 'daily_digest' | 'place_arrival'

export interface Notification {
  id: string
  rule_type: RuleType
  rule_id: string
  scheduled_for: string
  title: string
  body: string
  channel: NotificationChannel
  kind: ReminderKind
  dismissible: boolean
  snooze_minutes: number[]
  status: NotificationStatus
  sent_at: string | null
  delivered_at: string | null
  send_attempts: number
  error: string | null
  ack_action: AckAction | null
  ack_snoozed_minutes: number | null
  acked_at: string | null
}

export interface NextReminder {
  rule_type: RuleType
  title: string
  body: string
  kind: ReminderKind
  scheduled_for: string
}

export async function listNotifications(limit?: number): Promise<Notification[]> {
  const { data } = await client.get<Notification[]>('/notifications', { params: { limit } })
  return data
}

/** Predicted, not a real Notification row yet - see app/notify/next_up.py. Null if no enabled
 * schedule or ICS source has an upcoming occurrence in the lookahead window. */
export async function getNextNotification(): Promise<NextReminder | null> {
  const { data } = await client.get<NextReminder | null>('/notifications/next')
  return data
}

export interface HeartRateReading {
  id: string
  bpm: number
  recorded_at: string
}

export async function listHeartRate(since: Date, until: Date): Promise<HeartRateReading[]> {
  const { data } = await client.get<HeartRateReading[]>('/heart-rate', {
    params: { since: since.toISOString(), until: until.toISOString() },
  })
  return data
}

export async function createUser(email: string, timezone: string): Promise<User> {
  const { data } = await client.post<User>('/users', { email, timezone })
  return data
}

export async function getMe(): Promise<User> {
  const { data } = await client.get<User>('/users/me')
  return data
}

export async function updateMe(input: UserUpdateInput): Promise<User> {
  const { data } = await client.patch<User>('/users/me', input)
  return data
}

export async function listSchedules(): Promise<DailySchedule[]> {
  const { data } = await client.get<DailySchedule[]>('/schedules')
  return data
}

export async function createSchedule(input: DailyScheduleInput): Promise<DailySchedule> {
  const { data } = await client.post<DailySchedule>('/schedules', input)
  return data
}

export async function updateSchedule(
  id: string,
  input: Partial<DailyScheduleInput>,
): Promise<DailySchedule> {
  const { data } = await client.patch<DailySchedule>(`/schedules/${id}`, input)
  return data
}

export async function deleteSchedule(id: string): Promise<void> {
  await client.delete(`/schedules/${id}`)
}

export async function listIcsSources(): Promise<IcsSource[]> {
  const { data } = await client.get<IcsSource[]>('/ics-sources')
  return data
}

export async function createIcsSource(input: IcsSourceInput): Promise<IcsSource> {
  const { data } = await client.post<IcsSource>('/ics-sources', input)
  return data
}

export async function updateIcsSource(
  id: string,
  input: Partial<IcsSourceInput>,
): Promise<IcsSource> {
  const { data } = await client.patch<IcsSource>(`/ics-sources/${id}`, input)
  return data
}

export async function deleteIcsSource(id: string): Promise<void> {
  await client.delete(`/ics-sources/${id}`)
}

export async function listTodoLists(): Promise<TodoList[]> {
  const { data } = await client.get<TodoList[]>('/todo-lists')
  return data
}

export async function createTodoList(input: TodoListInput): Promise<TodoList> {
  const { data } = await client.post<TodoList>('/todo-lists', input)
  return data
}

export interface TodoListConnectionResult {
  ok: boolean
  detail: string | null
}

export async function testTodoListConnection(
  caldav_url: string,
  username: string | null,
  password: string | null,
): Promise<TodoListConnectionResult> {
  const { data } = await client.post<TodoListConnectionResult>('/todo-lists/test-connection', {
    caldav_url,
    username,
    password,
  })
  return data
}

/** Pass `clearPlace: true` to drop an existing place - omitting the place fields otherwise
 * leaves them unchanged, see app/schemas.py::TodoListUpdate. */
export async function updateTodoList(
  id: string,
  input: Partial<TodoListInput>,
  clearPlace = false,
): Promise<TodoList> {
  const { data } = await client.patch<TodoList>(`/todo-lists/${id}`, { ...input, clear_place: clearPlace })
  return data
}

export async function deleteTodoList(id: string): Promise<void> {
  await client.delete(`/todo-lists/${id}`)
}

export async function listTodoItems(id: string): Promise<TodoItem[]> {
  const { data } = await client.get<TodoItem[]>(`/todo-lists/${id}/items`)
  return data
}

export interface PhoneLocation {
  id: string
  latitude: number
  longitude: number
  accuracy_m: number | null
  recorded_at: string
}

export async function listLocations(since: Date, until: Date): Promise<PhoneLocation[]> {
  const { data } = await client.get<PhoneLocation[]>('/location', {
    params: { since: since.toISOString(), until: until.toISOString() },
  })
  return data
}

/** Null if the phone has never reported a position. */
export async function getLatestLocation(): Promise<PhoneLocation | null> {
  try {
    const { data } = await client.get<PhoneLocation>('/location/latest')
    return data
  } catch (e: any) {
    if (e?.response?.status === 404) return null
    throw e
  }
}

export async function ringPhone(): Promise<boolean> {
  const { data } = await client.post<{ delivered: boolean }>('/phone/ring')
  return data.delivered
}

/** Light, fire-and-forget notification - no dismiss/snooze options, no ack tracking. */
export async function sendAlert(message: string): Promise<boolean> {
  const { data } = await client.post<{ delivered: boolean }>('/alerts', { message })
  return data.delivered
}
