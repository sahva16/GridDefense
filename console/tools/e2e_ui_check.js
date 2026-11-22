// End-to-end check of the console in a real browser (Playwright + Chromium).
// Start the backend first, then:   node tools/e2e_ui_check.js [http://localhost:8000] [screenshot-folder]
// Exits with code 1 if any step fails or the page logs an error.
const { chromium } = require('playwright')
const fs = require('fs'), os = require('os'), path = require('path')

const URL = process.argv[2] || 'http://localhost:8000'
const SHOTS = process.argv[3] || null
const results = []
const step = async (name, fn) => {
  try { await fn(); results.push(['PASS', name]) } catch (e) { results.push(['FAIL', `${name}: ${e.message.split('\n')[0]}`]) }
}
const expect = (cond, msg) => { if (!cond) throw new Error(msg) }

;(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-webgl', '--ignore-gpu-blocklist'] })
  const page = await browser.newPage({ viewport: { width: 1600, height: 950 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  page.on('console', (m) => { if (m.type() === 'error' && !/422/.test(m.text())) errors.push(m.text()) })
  const shot = async (n) => SHOTS && page.screenshot({ path: path.join(SHOTS, `${n}.png`) })

  await step('console loads with a provenance badge', async () => {
    await page.goto(URL); await page.waitForSelector('.badge.as-btn', { timeout: 20000 })
    const t = await page.textContent('.badge.as-btn')
    expect(/verified|DEVELOPMENT|NOT verified/.test(t), `badge text "${t}"`)
    await shot('e2e_01_console')
  })
  await step('normal scenario S0 → no alarm', async () => {
    await page.locator('.scenarios li', { hasText: 'S0' }).locator('button').click()
    await page.waitForTimeout(3000)
    expect((await page.textContent('.state-block')).includes('NORMAL'), 'state is not NORMAL')
  })
  await step('attack scenario S3 → alarm and explanation', async () => {
    await page.locator('.scenarios li', { hasText: 'S3' }).locator('button').click()
    await page.waitForTimeout(3000)
    expect((await page.textContent('.state-block')).includes('ALARM'), 'state is not ALARM')
    expect((await page.textContent('.why-mini')).startsWith('Alarm:'), 'no explanation summary')
  })
  await step('Details: all five tabs render', async () => {
    await page.click('.view-tools >> text=Details')
    for (const t of ['Why', 'Measurements', 'Physics map', 'Localisation', 'Compare']) {
      await page.click(`.modal .tabs >> text=${t}`); await page.waitForTimeout(250)
    }
    await page.click('.modal .tabs >> text=Physics map')
    expect((await page.locator('.heat tbody tr').count()) === 14, 'heatmap does not have 14 rows')
    await page.click('.modal .tabs >> text=Localisation')
    expect(await page.locator('.verdict-head').count() === 1, 'no verdict')
    await shot('e2e_02_verdict')
    await page.keyboard.press('Escape')
  })
  await step('Upload: invalid CSV is rejected with a reason', async () => {
    const bad = path.join(os.tmpdir(), 'gd_bad.csv')
    fs.writeFileSync(bad, 'Vm_1,Vm_2\n1.0,abc\n')
    await page.click('.seg >> text=Upload')
    await page.setInputFiles('.upload input[type=file]', bad)
    await page.waitForSelector('.upload .err', { timeout: 10000 })
    const t = await page.textContent('.upload .err')
    expect(/rejected/i.test(t) && /missing required column/.test(t), `message: ${t}`)
    await shot('e2e_03_upload_rejected')
  })
  await step('Upload: valid one-row CSV is scored', async () => {
    const r = await page.request.get(`${URL}/api/sample.csv?i=5`)
    const good = path.join(os.tmpdir(), 'gd_good.csv'); fs.writeFileSync(good, await r.text())
    await page.setInputFiles('.upload input[type=file]', good)
    await page.waitForSelector('.upload .ok-line', { timeout: 15000 })
    expect((await page.textContent('.panel-meta')).includes('Uploaded snapshot'), 'detection panel does not show the upload')
  })
  await step('Large view toggles', async () => {
    await page.click('text=Large view'); await page.waitForTimeout(500)
    expect(await page.locator('.console.expanded').count() === 1, 'not expanded')
    await page.keyboard.press('Escape')
  })
  await step('Provenance panel shows all comparisons', async () => {
    await page.click('.badge.as-btn'); await page.waitForTimeout(400)
    const rows = await page.locator('.verif tbody tr').count()
    expect(rows >= 7, `only ${rows} rows`)
    await page.keyboard.press('Escape')
  })
  await step('Research page is labelled and separate', async () => {
    await page.click('text=Research results'); await page.waitForSelector('.research-tag')
    expect((await page.textContent('.research-tag')).includes('not live'), 'missing "not live" label')
    await shot('e2e_04_research')
  })
  await step('no errors in the page', async () => expect(errors.length === 0, errors.join(' | ')))
  await browser.close()
  for (const [s, n] of results) console.log(`${s}  ${n}`)
  process.exit(results.some(([s]) => s === 'FAIL') ? 1 : 0)
})()
