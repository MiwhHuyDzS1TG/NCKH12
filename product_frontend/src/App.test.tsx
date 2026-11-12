import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import App from './App'
import { BrowserRouter } from 'react-router-dom'

const bootstrap = {
  product: 'DUET / SPEAK',
  descriptor: 'NCKH12 Speaking Coach',
  demos: [
    { id: 'T001-D043', short_id: 'D043', display_name: 'Demo Student B', role: 'Main demo', thumbnail_url: '/thumb' },
    { id: 'T001-D064', short_id: 'D064', display_name: 'Demo Student A', role: 'Consistency example', thumbnail_url: '/thumb' },
    { id: 'T001-D048', short_id: 'D048', display_name: 'Demo Student C', role: 'Challenge case', thumbnail_url: '/thumb' },
  ],
  offline_ready: true,
  recent_count: 0,
  chatgpt: { connected: false, plan_usage_enabled: false, selected_model: null },
  scientific_scope: { frozen_research_overall_score: null, machine_intelligibility: null, holdout_processed: false, product_overall_version: 'nckh12-product-overall-practice-v1' },
}

test('home presents the two primary actions and frozen demo order', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => bootstrap }))
  window.history.replaceState({}, '', '/')
  render(<BrowserRouter><App /></BrowserRouter>)
  expect(await screen.findByRole('heading', { name: /Every Duet is a/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Try a Demo/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Assess a Duet/ })).toBeInTheDocument()
  expect((await screen.findAllByText(/Demo Student/)).map((node) => node.textContent)).toEqual([
    'Demo Student B', 'Demo Student A', 'Demo Student C',
  ])
})

test('selected Recent Video route starts the requested item without stale state', async () => {
  const calls: string[] = []
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input)
    calls.push(`${init?.method ?? 'GET'} ${path}`)
    if (path === '/api/bootstrap') return { ok: true, json: async () => bootstrap }
    if (path === '/api/media') return { ok: true, json: async () => ({ items: [] }) }
    if (path.includes('/assess')) {
      const mediaId = path.split('/')[3]
      return { ok: true, json: async () => ({ job_id: `job_${mediaId}`, media_id: mediaId, state: 'FAILED', message: 'fixture stop' }) }
    }
    return { ok: false, status: 404, json: async () => ({ detail: 'fixture missing' }) }
  })
  vi.stubGlobal('fetch', fetchMock)

  window.history.replaceState({}, '', '/assess?media=media_A')
  const first = render(<BrowserRouter><App /></BrowserRouter>)
  await waitFor(() => expect(calls).toContain('POST /api/media/media_A/assess'))
  first.unmount()
  cleanup()

  window.history.replaceState({}, '', '/assess?media=media_B')
  render(<BrowserRouter><App /></BrowserRouter>)
  await waitFor(() => expect(calls).toContain('POST /api/media/media_B/assess'))
  expect(calls.filter((call) => call.includes('/assess'))).toEqual([
    'POST /api/media/media_A/assess',
    'POST /api/media/media_B/assess',
  ])
})
