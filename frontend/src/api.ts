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

export async function createUser(email: string, timezone: string): Promise<User> {
  const { data } = await client.post<User>('/users', { email, timezone })
  return data
}

export async function getMe(): Promise<User> {
  const { data } = await client.get<User>('/users/me')
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
