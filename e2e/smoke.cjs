// End-to-end check against the real running app (no mocks).
// Usage: node e2e/smoke.cjs http://127.0.0.1:8790/ <screenshot-dir>
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE = process.argv[2] || 'http://127.0.0.1:8790/'
const OUT = process.argv[3] || 'e2e-out'
fs.mkdirSync(OUT, { recursive: true })
const results = []
let current = null
function check(name, ok, info = '') {
  results.push({ name, ok, info })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${info ? ' — ' + info : ''}`)
}

async function sheetButton(page, name) {
  await page.locator('.sheet').getByRole('button', { name, exact: true }).click()
}

;(async () => {
  const browser = await chromium.launch()
  const desktop = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  const consoleErrors = []
  desktop.on('pageerror', (e) => consoleErrors.push(e.message))
  const page = desktop
  current = page
  await page.goto(BASE)
  await page.getByText('Welcome to Bike Log').waitFor()
  check('empty state on a fresh database', true)
  await page.screenshot({ path: path.join(OUT, '01-empty-overview.png') })

  // bike
  await page.getByRole('link', { name: 'add your first bike' }).click()
  await page.getByRole('button', { name: 'Add bike' }).first().click()
  await page.locator('.sheet input').first().fill('TIME NXR')
  await sheetButton(page, 'Add bike')
  await page.getByRole('heading', { name: 'TIME NXR' }).waitFor()
  check('create bike', true)

  // three chains: A installed, B and C spare
  for (const [label, install] of [['Chain A', true], ['Chain B', false], ['Chain C', false]]) {
    await page.goto(BASE + '#/inventory')
    await page.getByRole('button', { name: 'Add part' }).click()
    await page.locator('.sheet').getByLabel('Name / label').fill(label)
    if (install) {
      await page.locator('.sheet').getByLabel('Install on (optional)').selectOption({ label: 'TIME NXR' })
      await page.locator('.sheet').getByLabel('Since').fill('2026-10-01')
    }
    await sheetButton(page, 'Add part')
    await page.getByRole('heading', { name: new RegExp(label) }).waitFor()
  }
  await page.goto(BASE + '#/inventory?tab=chains')
  await page.locator('.tile').filter({ hasText: 'Chain C' }).waitFor()
  check('three labelled chains', (await page.locator('.tile').count()) === 3)

  // hot wax via contextual log form on the bike
  await page.goto(BASE + '#/bikes')
  await page.getByRole('link', { name: /TIME NXR/ }).click()
  await page.getByRole('button', { name: 'Log maintenance' }).click()
  await page.locator('.sheet').getByRole('button', { name: 'Hot wax' }).click()
  await page.locator('.sheet input[type=checkbox]:checked').first().waitFor({ timeout: 5000 }).catch(() => {})
  const preselected = await page.locator('.sheet input[type=checkbox]:checked').count()
  check('installed chain preselected for hot wax', preselected === 1, `${preselected} checked`)
  await page.locator('.sheet').getByLabel('Date').fill('2026-10-01')
  await sheetButton(page, 'Save')
  await page.locator('.toast').filter({ hasText: 'Hot wax logged' }).waitFor()
  check('log hot wax in a few taps', true)

  // invalid ride keeps the form data
  await page.goto(BASE + '#/rides')
  await page.getByRole('button', { name: 'Add ride' }).click()
  await page.locator('.sheet').getByLabel('Date').fill('2026-10-02')
  await page.locator('.sheet').getByLabel('Distance').fill('-5')
  await page.locator('.sheet').getByLabel('Name (optional)').fill('Taunus loop')
  await sheetButton(page, 'Add ride')
  await page.locator('.sheet .form-error').waitFor()
  const kept = await page.locator('.sheet').getByLabel('Name (optional)').inputValue()
  check('recoverable error keeps entered data', kept === 'Taunus loop', await page.locator('.sheet .form-error').innerText())
  await page.locator('.sheet').getByLabel('Distance').fill('260')
  await sheetButton(page, 'Add ride')
  await page.locator('.toast').filter({ hasText: 'Chain A +260.0 km' }).waitFor()
  check('add manual ride shows mileage change', true)

  // overview: liquid wax due with explanation
  await page.goto(BASE + '#/')
  const liquid = page.locator('.task').filter({ hasText: 'Liquid-wax top-up' })
  await liquid.waitFor()
  const why = await liquid.locator('.task-why').innerText()
  check('260 km triggers liquid-wax task with explanation', /260 km since hot wax/.test(why) && /250–300 km/.test(why), why)
  await page.screenshot({ path: path.join(OUT, '02-overview-desktop.png'), fullPage: true })

  // snooze does not log maintenance
  await liquid.getByRole('button', { name: 'Snooze 7 days' }).click()
  await page.locator('.task').filter({ hasText: 'Liquid-wax top-up' }).getByText('Snoozed', { exact: true }).waitFor()
  check('snooze shows snoozed state', true)

  // swap chain A -> B on the bike
  await page.goto(BASE + '#/bikes')
  await page.getByRole('link', { name: /TIME NXR/ }).click()
  await page.locator('.setup li').filter({ hasText: 'Chain A' }).getByRole('button', { name: 'Change' }).click()
  await page.locator('.sheet .pick').filter({ hasText: 'Chain B' }).click()
  await page.locator('.sheet').getByLabel('Installed on').fill('2026-10-03')
  const keep = await page.locator('.sheet label.chip-on').innerText()
  check('chain outcome defaults to stored spare', /Stored as a reusable spare/.test(keep), keep)
  await page.locator('.sheet .form-actions').getByRole('button', { name: 'Preview' }).click()
  await page.locator('.sheet .notice-preview').waitFor()
  await page.locator('.sheet .form-actions').getByRole('button', { name: 'Replace' }).click()
  await page.locator('.setup li').filter({ hasText: 'Chain B' }).waitFor()
  check('swap chain via replace', true)
  await page.goto(BASE + '#/rides')
  await page.getByRole('button', { name: 'Add ride' }).click()
  await page.locator('.sheet').getByLabel('Date').fill('2026-10-04')
  await page.locator('.sheet').getByLabel('Distance').fill('40')
  await sheetButton(page, 'Add ride')
  await page.locator('.toast').filter({ hasText: 'Chain B +40.0 km' }).waitFor()
  check('mileage after swap goes to the new chain', true)

  // edit / exclude / restore a ride
  await page.locator('tr').filter({ hasText: '260 km' }).click()
  await page.locator('.sheet').getByRole('button', { name: 'Edit' }).click()
  await page.locator('.sheet').getByLabel('Distance').fill('250')
  await sheetButton(page, 'Preview mileage impact')
  const prev = await page.locator('.sheet .notice-preview').innerText()
  check('edit preview shows delta', /Chain A −10\.0 km/.test(prev), prev)
  await sheetButton(page, 'Save changes')
  await page.locator('.toast').filter({ hasText: 'Chain A −10.0 km' }).waitFor()
  await page.locator('.sheet').getByRole('button', { name: 'Remove from mileage' }).click()
  await page.locator('.toast').filter({ hasText: 'Chain A −250.0 km' }).waitFor()
  await page.locator('.sheet').getByRole('button', { name: 'Restore' }).click()
  await page.locator('.toast').filter({ hasText: 'Chain A +250.0 km' }).waitFor()
  check('edit, exclude, restore change totals once each', true)
  await page.keyboard.press('Escape')

  // component detail: contributions behind the mileage
  await page.goto(BASE + '#/inventory')
  await page.getByRole('link', { name: 'Chain A' }).click()
  await page.getByText('Where the kilometres come from').waitFor()
  const ledgerRows = await page.locator('.card').filter({ hasText: 'Where the kilometres come from' }).locator('tbody tr').count()
  check('ledger lists contributions', ledgerRows === 1, `${ledgerRows} rows`)
  await page.screenshot({ path: path.join(OUT, '03-component-detail.png'), fullPage: true })

  // CSV import twice
  await page.goto(BASE + '#/settings')
  const csv = 'source_id,date,distance_km,bike\nx-1,2026-10-05,30,TIME NXR\nx-2,2026-10-06,20,TIME NXR\n'
  const csvPath = path.join(OUT, 'rides.csv')
  fs.writeFileSync(csvPath, csv)
  await page.getByLabel('CSV file').setInputFiles(csvPath)
  await page.getByRole('button', { name: 'Import', exact: true }).click()
  await page.locator('.notice').filter({ hasText: '2 created' }).waitFor()
  await page.getByRole('button', { name: 'Import', exact: true }).click()
  await page.locator('.notice').filter({ hasText: '2 unchanged' }).waitFor()
  check('CSV import is repeatable without duplicates', true)
  const stravaText = await page.locator('.card').filter({ has: page.getByRole('heading', { name: 'Strava', exact: true }) }).innerText()
  check('Strava shown as not connected', /Not connected/.test(stravaText))
  await page.screenshot({ path: path.join(OUT, '04-settings.png'), fullPage: true })

  // spare stock: rear pads from stock 3 -> 2, old pads discarded, then undo restores
  await page.goto(BASE + '#/inventory')
  await page.getByRole('button', { name: 'Add spare stock' }).click()
  await page.locator('.sheet').getByLabel('What').selectOption('BRAKE_PADS')
  await page.locator('.sheet').getByLabel('Model (optional)').fill('L05A-RF')
  await page.locator('.sheet').getByLabel('In stock now (optional)').fill('3')
  await page.locator('.sheet').getByLabel('Storage location (optional)').fill('Workshop drawer')
  await page.locator('.sheet').getByLabel('Minimum stock (optional)').fill('1')
  await sheetButton(page, 'Add')
  const padRow = page.locator('.list.rows li').filter({ hasText: 'L05A-RF' })
  await padRow.filter({ hasText: '3 new sets' }).waitFor()
  check('stock row reads "3 new sets · Workshop drawer · Minimum: 1"', /3 new sets · Workshop drawer · Minimum: 1/.test(await padRow.innerText()))
  await page.getByRole('button', { name: 'Add part' }).click()
  await page.locator('.sheet').getByLabel('Type').selectOption('BRAKE_PADS')
  await page.locator('.sheet').getByLabel('Name / label').fill('Rear pads')
  await page.locator('.sheet').getByLabel('Install on (optional)').selectOption({ label: 'TIME NXR' })
  await page.locator('.sheet').getByLabel('Position').selectOption('REAR_PADS')
  await page.locator('.sheet').getByLabel('Since').fill('2026-10-01')
  await sheetButton(page, 'Add part')
  await page.getByRole('heading', { name: /Rear pads/ }).waitFor()
  await page.getByRole('button', { name: 'Replace', exact: true }).click()
  await page.locator('.sheet .pick').filter({ hasText: 'One from stock' }).waitFor()
  const suggested = await page.locator('.sheet label.chip-on').innerText()
  check('replace preselects stock and suggests discarding old pads', /Discarded/.test(suggested), suggested)
  await page.screenshot({ path: path.join(OUT, '07-replace-pads.png'), fullPage: true })
  await page.locator('.sheet .form-actions').getByRole('button', { name: 'Replace' }).click()
  await page.locator('.toast').filter({ hasText: 'installed' }).waitFor()
  await page.goto(BASE + '#/inventory')
  await padRow.filter({ hasText: '2 new sets' }).waitFor()
  check('stock goes from 3 to 2 sets after replacement', true)
  await page.goto(BASE + '#/inventory?tab=history')
  await page.locator('.list li').filter({ hasText: 'Rear pads' }).filter({ hasText: 'Discarded' }).first().waitFor()
  check('old pads shown as discarded in history', true)
  page.once('dialog', (d) => d.accept('test undo'))
  await page.locator('.list.rows li').filter({ hasText: 'Replace Rear pads' }).getByRole('button', { name: 'Undo' }).click()
  await page.locator('.toast').filter({ hasText: 'Undone' }).waitFor()
  await page.goto(BASE + '#/inventory')
  await padRow.filter({ hasText: '3 new sets' }).waitFor()
  check('undo restores stock to 3 and reinstalls old pads', true)
  await page.screenshot({ path: path.join(OUT, '08-inventory.png'), fullPage: true })

  // groupset import: whole Ultegra Di2 R8100 group in one action, then undo
  await page.goto(BASE + '#/bikes')
  await page.getByRole('link', { name: /TIME NXR/ }).click()
  await page.getByRole('button', { name: 'Add groupset' }).click()
  await page.locator('.sheet').getByLabel('Chainrings').selectOption('50-34')
  await page.locator('.sheet .groupset-items li').filter({ hasText: 'outer chainring 50T' }).waitFor()
  const chainRow = await page.locator('.sheet .groupset-items li').filter({ hasText: 'CN-M8100' }).innerText()
  check('groupset plan keeps the installed chain and adds the new one as a spare', /already has Chain/.test(chainRow), chainRow)
  await page.screenshot({ path: path.join(OUT, '09-groupset.png'), fullPage: true })
  await page.locator('.sheet').getByRole('button', { name: /^Add \d+ parts$/ }).click()
  await page.locator('.toast').filter({ hasText: 'parts added' }).waitFor()
  await page.locator('.list.setup').getByRole('link', { name: 'Ultegra crankset (TIME NXR)' }).waitFor()
  await page.locator('.list.setup').getByRole('link', { name: 'Ultegra outer chainring 50T (TIME NXR)' }).waitFor()
  check('groupset import installs crankset and chainrings', true)
  await page.goto(BASE + '#/inventory?tab=history')
  page.once('dialog', (d) => d.accept('test undo'))
  await page.locator('.list.rows li').filter({ hasText: 'Add groupset' }).getByRole('button', { name: 'Undo' }).click()
  await page.locator('.toast').filter({ hasText: 'Undone' }).waitFor()
  await page.goto(BASE + '#/bikes')
  await page.getByRole('link', { name: /TIME NXR/ }).click()
  await page.getByRole('heading', { name: 'TIME NXR' }).waitFor()
  check('undo removes the whole groupset again', (await page.locator('.list.setup').getByRole('link', { name: 'Ultegra crankset (TIME NXR)' }).count()) === 0)

  // mobile viewport
  const phone = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })
  phone.on('pageerror', (e) => consoleErrors.push(e.message))
  await phone.goto(BASE)
  await phone.locator('.task').first().waitFor()
  const navVisible = await phone.locator('.sidebar nav').isVisible()
  const overflow = await phone.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
  check('mobile: bottom navigation visible, no horizontal overflow', navVisible && !overflow, `overflow=${overflow}`)
  await phone.screenshot({ path: path.join(OUT, '05-mobile-overview.png'), fullPage: true })
  await phone.goto(BASE + '#/maintenance')
  await phone.getByRole('button', { name: 'Log maintenance' }).click()
  await phone.locator('.sheet').getByRole('button', { name: 'Measure chain wear' }).click()
  await phone.locator('.sheet').getByLabel('Measurement').fill('0.3')
  await phone.screenshot({ path: path.join(OUT, '06-mobile-log.png') })
  await phone.locator('.sheet').getByRole('button', { name: 'Save', exact: true }).click()
  await phone.locator('.toast').filter({ hasText: 'Measure chain wear logged' }).waitFor()
  check('mobile: log chain wear measurement', true)
  for (const route of ['#/bikes', '#/rides', '#/inventory', '#/inventory?tab=history', '#/inventory?tab=shopping', '#/settings']) {
    await phone.goto(BASE + route)
    await phone.waitForTimeout(400)
    const of = await phone.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
    check(`mobile: ${route} fits the screen`, !of)
  }
  check('no uncaught page errors', consoleErrors.length === 0, consoleErrors.join(' | '))
  await browser.close()
  const failed = results.filter((r) => !r.ok)
  fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify(results, null, 2))
  console.log(`\n${results.length - failed.length}/${results.length} checks passed`)
  process.exit(failed.length ? 1 : 0)
})().catch(async (e) => {
  console.error('E2E ABORTED:', e.message)
  if (current) await current.screenshot({ path: path.join(OUT, 'abort.png'), fullPage: true }).catch(() => {})
  process.exit(2)
})
