// Sample database check against the real running app started on a NEW data directory WITHOUT --no-sample.
// Usage: node e2e/sample.cjs http://127.0.0.1:8791/ <screenshot-dir>
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.argv[2] || 'http://127.0.0.1:8791/'
const OUT = process.argv[3] || 'e2e-out'
fs.mkdirSync(OUT, { recursive: true })
let failed = 0
function check(name, ok, info = '') {
  if (!ok) failed++
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? ' — ' + info : ''}`)
}

;(async () => {
  const browser = await chromium.launch()
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  try {
    await page.goto(BASE)
    await page.getByText('Sample data.').waitFor()
    check('sample banner on a new database', true)
    await page.goto(BASE + '#/bikes')
    await page.getByRole('link', { name: /Aurora SL/ }).waitFor()
    check('sample bikes listed', (await page.getByRole('link', { name: /Winter Allroad/ }).count()) === 1)
    await page.screenshot({ path: path.join(OUT, 'sample-bikes.png'), fullPage: true })
    await page.getByRole('link', { name: /Winter Allroad/ }).click()
    await page.getByText('Frame and fork inspection after a crash').first().waitFor()
    check('sample crash asks for a frame inspection', true)
    await page.getByRole('link', { name: 'Settings → Fresh start' }).click()
    await page.getByLabel('Type RESET to confirm').fill('RESET')
    await page.getByRole('button', { name: 'Reset database' }).click()
    await page.getByText('The database is empty now.').waitFor()
    await page.waitForTimeout(500)
    check('Fresh start removes the sample banner', (await page.getByText('Sample data.').count()) === 0)
    check('no page errors', errors.length === 0, errors.join('; '))
  } catch (e) {
    failed++
    console.log('E2E ABORTED: ' + e.message)
    await page.screenshot({ path: path.join(OUT, 'sample-abort.png'), fullPage: true })
  }
  await browser.close()
  console.log(failed ? `${failed} sample checks failed` : 'sample checks passed')
  process.exit(failed ? 1 : 0)
})()
