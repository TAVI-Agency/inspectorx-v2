// PDF-экспорт питч-дека: каждый слайд — страница 1920x1080.
// Запуск: node deck/export-pdf.mjs  (нужен поднятый deck-сервер, по умолчанию :5199)
import { chromium } from 'playwright';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const dir = path.dirname(fileURLToPath(import.meta.url));
const base = process.env.DECK_BASE || 'http://localhost:5199/';
const out = path.join(dir, 'InspectorX-Pitch-Deck.pdf');

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto(base, { waitUntil: 'networkidle' });
await page.waitForSelector('deck-stage section');

// Рельс миниатюр и оверлей — только для экрана, в печать не идут.
await page.addStyleTag({
  content: `
    deck-stage::part(rail), deck-stage::part(overlay) { display: none !important; }
    * { animation: none !important; transition: none !important; }
  `,
});

// Только light-DOM: locator видит и клоны миниатюр в shadow root рельса.
const count = await page.evaluate(() => document.querySelectorAll('deck-stage > section').length);
await page.emulateMedia({ media: 'print' });
await page.pdf({
  path: out,
  width: '1920px',
  height: '1080px',
  printBackground: true,
  pageRanges: `1-${count}`,
});

await browser.close();
console.log(`PDF: ${out} (${count} слайдов)`);
