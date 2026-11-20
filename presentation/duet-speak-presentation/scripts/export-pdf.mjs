import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const baseUrl = process.env.PRESENTATION_URL ?? 'http://127.0.0.1:4173';
const output = path.resolve('output/pdf/DUET-SPEAK-NCKH12.pdf');
await fs.mkdir(path.dirname(output), { recursive: true });
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH ?? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
});
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
await page.goto(`${baseUrl}/?print=1`, { waitUntil: 'networkidle' });
await page.evaluate(() => document.fonts.ready);
await page.emulateMedia({ media: 'print', reducedMotion: 'reduce' });
await page.pdf({
  path: output,
  width: '13.333333in',
  height: '7.5in',
  printBackground: true,
  preferCSSPageSize: true,
  margin: { top: '0', right: '0', bottom: '0', left: '0' },
});
await browser.close();
console.log(output);
