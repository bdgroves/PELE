// Screenshots of the live site, run in Actions (real network: webcams, USGS plots, map tiles).
import { chromium } from 'playwright';
const b = await chromium.launch();
const errs = [];
for (const [name, vp] of [['desk', { width: 1366, height: 900 }], ['phone', { width: 390, height: 844 }]]) {
  const p = await b.newPage({ viewport: vp });
  p.on('pageerror', e => errs.push(`${name}: ${e.message}`));
  p.on('requestfailed', r => errs.push(`${name} failed: ${r.url().slice(0, 120)}`));
  await p.goto('https://bdgroves.github.io/PELE/?v=' + Date.now(), { waitUntil: 'networkidle' });
  await p.waitForTimeout(3000);
  await p.screenshot({ path: `tools/shots/${name}-overview.png`, fullPage: true });
  for (const t of ['webcams', 'earthquakes', 'monitoring', 'volcanoes', 'eruption']) {
    await p.click(`.nav-tab[data-tab="${t}"]`);
    await p.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 600) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); } window.scrollTo(0, 0); });
    await p.waitForTimeout(3500);
    await p.screenshot({ path: `tools/shots/${name}-${t}.png`, fullPage: true });
  }
}
console.log(errs.join('\n') || 'no errors');
import('fs').then(fs => fs.writeFileSync('tools/shots/errors.txt', errs.join('\n') || 'no errors'));
await b.close();
