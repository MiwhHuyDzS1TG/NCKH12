import { chromium } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';

const baseUrl = process.env.PRESENTATION_URL ?? 'http://127.0.0.1:4173';
const slides = [
  ['s01',1],['s02',3],['s03',3],['s04',6],['s05',3],['s06',6],['s07',5],
  ['s08',5],['s09',5],['s10',4],['s11',4],['s12',3],['s13',2],['s14',2],
  ['a01',1],['a02',1],['a03',1],['a04',1],
];
const viewports = [[1920,1080],[1366,768]];
const browser = await chromium.launch({
  headless: true,
  executablePath: process.env.CHROME_PATH ?? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
});

for (const [width,height] of viewports) {
  const outDir = path.resolve(`screenshots/${width}x${height}`);
  await fs.mkdir(outDir, { recursive: true });
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: 1 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  const errors = [];
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('pageerror', (error) => errors.push(error.message));
  for (const [id,fragment] of slides) {
    await page.goto(`${baseUrl}/#/${id}-f${fragment}`, { waitUntil: 'networkidle' });
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(750);
    await page.screenshot({ path: path.join(outDir, `${id}.png`), fullPage: false });
  }
  await fs.writeFile(path.join(outDir, 'console-errors.json'), JSON.stringify(errors, null, 2));
  await page.close();
}

await browser.close();
console.log('Captured 18 slides at 1920x1080 and 1366x768.');
