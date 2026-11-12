import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
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

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function criterion(key: 'pronunciation' | 'fluency' | 'prosody', value: number | null) {
  const labels = { pronunciation: 'Pronunciation', fluency: 'Fluency', prosody: 'Prosody' }
  const descriptions = { pronunciation: 'Sound accuracy and clarity', fluency: 'Flow, continuity and pausing', prosody: 'Stress, rhythm and intonation' }
  return {
    key, label: labels[key], description: descriptions[key], value,
    display_value: value == null ? null : Math.round(value * 10) / 10,
    unit: 'SCALE_1_5', scale_max: 5, available: value != null,
    status: value == null ? 'UNAVAILABLE' : key === 'fluency' ? 'USABLE' : 'PRELIMINARY',
    badge: key === 'fluency' ? 'Usable criterion' : 'Preliminary',
    caveat: key === 'pronunciation' ? 'Based on a limited development score range.' : null,
  }
}

function resultFixture(pairId: string, pronunciation: number | null) {
  const fluency = 4.61
  const prosody = pronunciation == null ? null : 3.9184
  const completeness = 97
  return {
    id: pairId, pair_id: pairId, display_name: 'Demo Student', source_mode: 'FROZEN_DEMO', status: 'COMPLETE',
    target_topic: 'One memorable event', target_text: 'Target text', transcript: 'Learner transcript',
    criteria: { version: 'nckh12-product-criteria-v1', items: {
      pronunciation: criterion('pronunciation', pronunciation),
      fluency: criterion('fluency', fluency),
      prosody: criterion('prosody', prosody),
      completeness: { key: 'completeness', label: 'Reading Completeness', description: 'Target passage matched by ASR', value: completeness, display_value: completeness, unit: 'PERCENT', scale_max: 100, available: true, status: 'USABLE', badge: 'ASR-assisted coverage', caveat: 'ASR differences are not confirmed learner reading errors.' },
    } },
    completeness: { coverage: .97, matched_word_count: 135, possible_asr_uncertainty: [], asr_insertions: [], warning: 'ASR-assisted.' },
    evidence: { fluency: { speech_rate_wpm: 170.6, long_pause_count: 1, longest_pause_sec: .8, mean_length_of_run_words: 9.2 }, word_review_prompts: [{ word: 'gowns', interpretation: 'review' }] },
    feedback: { strength: { text: 'Strength.' }, focus_next: { text: 'Focus.' }, try_this: { text: 'Try.' }, source: 'DETERMINISTIC' },
    media: { video_url: '/video', audio_url: '/audio' }, model_failures: [],
    provenance: { source_mode: 'FROZEN_DEMO', canonical_source: 'RAW_COMPLETED_DUET', audio_source_type: 'RAW_CROPPED', genuine_frozen_inference: true, research_membership: false },
    machine_intelligibility: null,
    overall_practice_score: pronunciation == null ? null : { version: 'v1', value: 4.3, display_value: 4.3, scale_max: 5, status: 'DESCRIPTIVE_PRODUCT_COMPOSITE', label: 'Overall Practice Score', methodology_note: 'Equal weighted.', student_note: 'Not standardized.', presenter_designation: 'UNVALIDATED_PRODUCT_COMPOSITE', inputs: { pronunciation, fluency, prosody, reading_completeness: 4.88 }, machine_intelligibility_included: false, research_validated: false },
    holdout_processed: false,
  }
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

test('all frozen demos bind numeric criteria without decorative numbering', async () => {
  const demos = [
    ['T001-D043', 3.795],
    ['T001-D064', 3.7609],
    ['T001-D048', 3.864],
  ] as const
  for (const [pairId, pronunciation] of demos) {
    const fixture = resultFixture(pairId, pronunciation)
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/api/bootstrap') return { ok: true, json: async () => bootstrap }
      if (path === `/api/demos/${pairId}`) return { ok: true, json: async () => fixture }
      return { ok: false, status: 404, json: async () => ({ detail: 'fixture missing' }) }
    }))
    window.history.replaceState({}, '', `/results/demo/${pairId}`)
    const view = render(<BrowserRouter><App /></BrowserRouter>)
    const pronunciationModule = (await screen.findByRole('heading', { name: 'Pronunciation' })).closest('.pronunciation') as HTMLElement
    expect(within(pronunciationModule).getByText(fixture.criteria.items.pronunciation.display_value!.toFixed(1), { exact: false })).toBeInTheDocument()
    expect(within(pronunciationModule).queryByText('03')).not.toBeInTheDocument()
    expect(within(pronunciationModule).getByText('Preliminary')).toBeInTheDocument()
    expect(within(view.container.querySelector('.criterion-feature') as HTMLElement).getByText(fixture.criteria.items.fluency.display_value!.toFixed(1), { exact: false })).toBeInTheDocument()
    expect(within(view.container.querySelector('.prosody') as HTMLElement).getByText(fixture.criteria.items.prosody.display_value!.toFixed(1), { exact: false })).toBeInTheDocument()
    expect(view.container.querySelector('.criterion-number')).toHaveTextContent(`${fixture.criteria.items.completeness.display_value}%`)
    expect(view.container.querySelector('.overall-value')).toHaveTextContent(fixture.overall_practice_score!.display_value.toFixed(1))
    view.unmount()
    cleanup()
  }
})

test('partial result explains unavailable criterion and withholds Overall', async () => {
  const fixture = resultFixture('media_partial', null)
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const path = String(input)
    if (path === '/api/bootstrap') return { ok: true, json: async () => bootstrap }
    if (path === '/api/media/media_partial/result') return { ok: true, json: async () => fixture }
    return { ok: false, status: 404, json: async () => ({ detail: 'fixture missing' }) }
  }))
  window.history.replaceState({}, '', '/results/media/media_partial')
  render(<BrowserRouter><App /></BrowserRouter>)
  const module = (await screen.findByRole('heading', { name: 'Pronunciation' })).closest('.pronunciation') as HTMLElement
  expect(within(module).getByText('Unavailable')).toBeInTheDocument()
  expect(within(module).queryByText('N/A')).not.toBeInTheDocument()
  expect(screen.getByText('Overall Practice Score unavailable')).toBeInTheDocument()
})
