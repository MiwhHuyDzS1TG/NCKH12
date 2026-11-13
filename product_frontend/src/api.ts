import type { AssessmentResult, Bootstrap, JobState, MediaItem } from './types'

export class ApiError extends Error {
  constructor(message: string, public code = 'request_failed', public status = 500) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(payload.detail?.message ?? payload.detail ?? 'The request could not be completed.', payload.detail?.code, response.status)
  }
  return payload as T
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function validCriterion(value: unknown): boolean {
  if (!isObject(value)) return false
  return typeof value.key === 'string'
    && typeof value.label === 'string'
    && typeof value.description === 'string'
    && typeof value.available === 'boolean'
    && (value.value === null || typeof value.value === 'number')
    && (value.display_value === null || typeof value.display_value === 'number')
    && typeof value.badge === 'string'
}

export function normalizeAssessmentResult(value: unknown): AssessmentResult {
  if (!isObject(value) || !isObject(value.criteria) || !isObject(value.criteria.items)
      || !isObject(value.feedback) || !isObject(value.media) || !isObject(value.evidence)
      || !isObject(value.completeness)) {
    throw new ApiError("We couldn't load this assessment.", 'invalid_result_contract', 502)
  }
  const items = value.criteria.items
  const required = ['pronunciation', 'fluency', 'prosody', 'completeness']
  if (!required.every((key) => validCriterion(items[key]))
      || typeof value.id !== 'string'
      || typeof value.status !== 'string'
      || typeof value.display_name !== 'string'
      || !isObject(value.feedback.strength)
      || !isObject(value.feedback.focus_next)
      || !isObject(value.feedback.try_this)
      || typeof value.feedback.strength.text !== 'string'
      || typeof value.feedback.focus_next.text !== 'string'
      || typeof value.feedback.try_this.text !== 'string'
      || typeof value.media.video_url !== 'string') {
    throw new ApiError("We couldn't load this assessment.", 'invalid_result_contract', 502)
  }
  return value as unknown as AssessmentResult
}

export const api = {
  bootstrap: () => request<Bootstrap>('/api/bootstrap'),
  demos: () => request<Bootstrap>('/api/bootstrap').then((x) => x.demos),
  demoResult: (id: string) => request<unknown>(`/api/demos/${encodeURIComponent(id)}`).then(normalizeAssessmentResult),
  recent: () => request<{ items: MediaItem[] }>('/api/media').then((x) => x.items),
  upload: (file: File) => {
    const body = new FormData()
    body.append('file', file)
    return request<{ item: MediaItem; created: boolean }>('/api/media/upload', { method: 'POST', body })
  },
  previewTikTok: (url: string) => request<{ title: string; author_name: string; thumbnail_url?: string; resolved_url: string }>('/api/tiktok/preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }),
  }),
  importTikTok: (url: string, permission_confirmed: boolean) => request<{ item: MediaItem; created: boolean }>('/api/tiktok/import', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url, permission_confirmed }),
  }),
  startAssessment: (mediaId: string) => request<JobState>(`/api/media/${encodeURIComponent(mediaId)}/assess`, { method: 'POST' }),
  job: (jobId: string) => request<JobState>(`/api/jobs/${encodeURIComponent(jobId)}`),
  mediaResult: (mediaId: string) => request<unknown>(`/api/media/${encodeURIComponent(mediaId)}/result`).then(normalizeAssessmentResult),
  removeMedia: (mediaId: string) => request<{ removed: true }>(`/api/media/${encodeURIComponent(mediaId)}`, { method: 'DELETE' }),
  connectChatGPT: () => request<{ state: string }>('/api/presenter/chatgpt/connect', { method: 'POST', headers: { 'X-Presenter': '1' } }),
  disconnectChatGPT: () => request<{ connected: false }>('/api/presenter/chatgpt/disconnect', { method: 'POST', headers: { 'X-Presenter': '1' } }),
  selectModel: (slug: string) => request<{ selected_model: string }>('/api/presenter/chatgpt/model', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Presenter': '1' }, body: JSON.stringify({ slug }),
  }),
}
