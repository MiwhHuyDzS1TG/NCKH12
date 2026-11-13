import { expect, test } from '@playwright/test'

const demos = [
  ['T001-D043', '3.8'],
  ['T001-D064', '3.8'],
  ['T001-D048', '3.9'],
] as const

test('primary routes and assessment alias survive direct navigation and refresh', async ({ page }) => {
  for (const path of ['/', '/assessment', '/recent']) {
    await page.goto(path)
    await expect(page.locator('#root > *')).toHaveCount(1)
    await expect(page.locator('body')).not.toBeEmpty()
    if (path === '/assessment') await expect(page).toHaveURL(/\/assess$/)
    await page.reload()
    await expect(page.locator('#root > *')).toHaveCount(1)
  }
})

for (const [pairId, pronunciation] of demos) {
  test(`${pairId} direct result and refresh render the frozen contract`, async ({ page }) => {
    const pageErrors: string[] = []
    page.on('pageerror', (error) => pageErrors.push(error.message))
    await page.goto(`/results/demo/${pairId}`)
    await expect(page.getByRole('heading', { name: 'Overall Practice Score' })).toBeVisible()
    await expect(page.locator('.pronunciation .editorial-score')).toContainText(pronunciation)
    await page.reload()
    await expect(page.getByRole('heading', { name: 'Overall Practice Score' })).toBeVisible()
    expect(pageErrors).toEqual([])
  })
}

test('home navigation, browser back and forward keep the selected result', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: /Try a Demo/ }).click()
  await expect(page).toHaveURL(/\/assess/)
  await page.locator('.demo-rail button').filter({ hasText: 'D043' }).click()
  await expect(page).toHaveURL(/T001-D043/)
  await expect(page.getByRole('heading', { name: 'Overall Practice Score' })).toBeVisible()
  await page.goBack()
  await expect(page).toHaveURL(/\/assess/)
  await page.goForward()
  await expect(page).toHaveURL(/T001-D043/)
  await expect(page.getByRole('heading', { name: 'Overall Practice Score' })).toBeVisible()
})

test('unknown result and API failure render recoverable states', async ({ page }) => {
  await page.goto('/results/demo/NOT-A-DEMO')
  await expect(page.getByRole('heading', { name: 'This assessment result could not be found.' })).toBeVisible()

  await page.route('**/api/demos/T001-D064', (route) => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'temporary' }) }))
  await page.goto('/results/demo/T001-D064')
  await expect(page.getByRole('heading', { name: "We couldn't load this assessment." })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Back to Home' })).toBeVisible()
})

test('media failure does not remove a valid assessment result', async ({ page }) => {
  await page.route('**/api/demos/T001-D043/video', (route) => route.abort())
  await page.route('**/api/demos/T001-D043/audio', (route) => route.abort())
  await page.goto('/results/demo/T001-D043')
  await expect(page.getByRole('heading', { name: 'Overall Practice Score' })).toBeVisible()
  await expect(page.getByText('Media preview unavailable')).toBeVisible()
  await expect(page.getByText('Learner audio preview unavailable')).toBeVisible()
  await expect(page.locator('.pronunciation .editorial-score')).toContainText('3.8')
})

test('partial result keeps valid criteria and withholds unavailable measures', async ({ page }) => {
  const criterion = (key: string, value: number | null, badge: string) => ({
    key, label: key === 'fluency' ? 'Fluency' : key === 'prosody' ? 'Prosody' : key === 'pronunciation' ? 'Pronunciation' : 'Reading Completeness',
    description: 'Measured evidence', value, display_value: value, unit: key === 'completeness' ? 'PERCENT' : 'SCALE_1_5', scale_max: key === 'completeness' ? 100 : 5,
    available: value !== null, status: value === null ? 'UNAVAILABLE' : 'USABLE', badge, caveat: null,
  })
  const partial = {
    id: 'e2e-partial', pair_id: 'T001-LIVE', display_name: 'Completed Duet', source_mode: 'LIVE_ANALYSIS', status: 'PARTIAL',
    target_topic: 'One memorable event', target_text: 'Target', transcript: 'Transcript',
    criteria: { version: 'nckh12-product-criteria-v1', items: {
      pronunciation: criterion('pronunciation', null, 'Preliminary'), fluency: criterion('fluency', 4.2, 'Usable criterion'),
      prosody: criterion('prosody', null, 'Preliminary'), completeness: criterion('completeness', 88, 'ASR-assisted coverage'),
    } },
    completeness: { coverage: .88, matched_word_count: 100, possible_asr_uncertainty: [], asr_insertions: [], warning: 'ASR-assisted.' },
    evidence: { fluency: { speech_rate_wpm: 150, long_pause_count: 2 }, word_review_prompts: [] },
    feedback: { strength: { text: 'Keep your steady flow.' }, focus_next: { text: 'Follow the passage.' }, try_this: { text: 'Try one more take.' }, source: 'DETERMINISTIC' },
    media: { video_url: '/missing-private-video', audio_url: null }, model_failures: [],
    provenance: { source_mode: 'LIVE_ANALYSIS', canonical_source: 'RAW_COMPLETED_DUET', audio_source_type: 'RAW_CROPPED', genuine_frozen_inference: true, research_membership: false },
    machine_intelligibility: null, overall_practice_score: null, holdout_processed: false,
  }
  await page.route('**/api/media/e2e-partial/result', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(partial) }))
  await page.goto('/results/media/e2e-partial')
  await expect(page.locator('.pronunciation')).toContainText('Unavailable')
  await expect(page.locator('.prosody')).toContainText('Unavailable')
  await expect(page.locator('.criterion-feature')).toContainText('4.2')
  await expect(page.getByText('Overall Practice Score unavailable')).toBeVisible()
})
