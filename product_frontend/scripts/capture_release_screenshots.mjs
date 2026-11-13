import { chromium } from '@playwright/test'
import { mkdir } from 'node:fs/promises'
import { resolve } from 'node:path'
import process from 'node:process'

const baseURL = process.env.NCKH12_SCREENSHOT_URL || 'http://127.0.0.1:8765'
const output = resolve(process.cwd(), '..', 'ui_evidence', 'final_release')

await mkdir(output, { recursive: true })
const browser = await chromium.launch({ channel: 'chrome' })

async function capture(name, route, options = {}) {
  const context = await browser.newContext({
    viewport: options.viewport || { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    reducedMotion: 'reduce',
  })
  const page = await context.newPage()
  if (options.emptyLibrary) {
    await page.route('**/api/media', (request) => request.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    }))
  }
  await page.goto(`${baseURL}${route}`, { waitUntil: 'networkidle' })
  await page.locator('main').waitFor({ state: 'visible' })
  if (options.blurMedia) {
    await page.locator('video').evaluateAll((elements) => {
      for (const element of elements) {
        element.style.filter = 'blur(18px)'
        element.style.transform = 'scale(1.04)'
      }
    })
  }
  if (options.openEvidence) {
    await page.getByRole('button', { name: /Explore the evidence/i }).click()
    const evidence = page.locator('.evidence-content')
    await evidence.waitFor({ state: 'visible' })
    await evidence.scrollIntoViewIfNeeded()
  }
  await page.locator('.skip-link').evaluate((element) => { element.style.display = 'none' })
  if (options.section) {
    await page.locator(options.section).screenshot({ path: resolve(output, name) })
  } else {
    await page.screenshot({ path: resolve(output, name), fullPage: Boolean(options.fullPage) })
  }
  await context.close()
}

try {
  await capture('01_HOME.png', '/')
  await capture('02_ASSESSMENT.png', '/assess')
  await capture('03_RESULTS_D043.png', '/results/demo/T001-D043', {
    fullPage: true,
    blurMedia: true,
  })
  await capture('04_RESULTS_EVIDENCE.png', '/results/demo/T001-D043', {
    openEvidence: true,
    section: '.evidence-section',
  })
  await capture('05_RECENT_VIDEOS.png', '/recent', { emptyLibrary: true })
  await capture('07_MOBILE_RESULTS.png', '/results/demo/T001-D043', {
    viewport: { width: 390, height: 844 },
    blurMedia: true,
  })
} finally {
  await browser.close()
}
