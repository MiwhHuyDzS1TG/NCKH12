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

export const api = {
  bootstrap: () => request<Bootstrap>('/api/bootstrap'),
  demos: () => request<Bootstrap>('/api/bootstrap').then((x) => x.demos),
  demoResult: (id: string) => request<AssessmentResult>(`/api/demos/${encodeURIComponent(id)}`),
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
  mediaResult: (mediaId: string) => request<AssessmentResult>(`/api/media/${encodeURIComponent(mediaId)}/result`),
  removeMedia: (mediaId: string) => request<{ removed: true }>(`/api/media/${encodeURIComponent(mediaId)}`, { method: 'DELETE' }),
  connectChatGPT: () => request<{ state: string }>('/api/presenter/chatgpt/connect', { method: 'POST', headers: { 'X-Presenter': '1' } }),
  disconnectChatGPT: () => request<{ connected: false }>('/api/presenter/chatgpt/disconnect', { method: 'POST', headers: { 'X-Presenter': '1' } }),
  selectModel: (slug: string) => request<{ selected_model: string }>('/api/presenter/chatgpt/model', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Presenter': '1' }, body: JSON.stringify({ slug }),
  }),
}
