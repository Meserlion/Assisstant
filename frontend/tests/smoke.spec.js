import { test, expect } from '@playwright/test'

/**
 * Deploy gate for the frontend.
 *
 * The backend health check (`/api/health`) returns 200 no matter how broken the UI is,
 * so before this existed a change that removed navigation — or crashed React outright —
 * would deploy green and nobody would find out until they opened the app.
 *
 * These tests assert the shell is intact. They do NOT assert that data loads: there is no
 * backend in CI, so every API call fails by design. Keep it that way — asserting on data
 * would make this flaky, and flaky deploy gates get disabled.
 */

const TABS = ['Notes', 'Merge', 'Ask', 'Calendar']

test.beforeEach(async ({ page }) => {
  // Everything is gated behind an API key in localStorage (App.jsx: `if (!ready) return
  // <ApiKeySetup/>`). Seed a dummy one so the real UI renders. The value is never sent
  // anywhere meaningful — requests fail regardless, which is fine.
  await page.addInitScript(() => window.localStorage.setItem('api_key', 'smoke-test-key'))
})

test('app renders without crashing', async ({ page }) => {
  const pageErrors = []
  page.on('pageerror', (e) => pageErrors.push(e.message))

  await page.goto('/')

  // A React crash leaves #root empty while the HTTP response is still a healthy 200.
  await expect(page.locator('#root')).not.toBeEmpty()
  expect(pageErrors.join(' | ')).toBe('')
})

test('header navigation is present', async ({ page }) => {
  await page.goto('/')

  const nav = page.locator('header nav')
  await expect(nav).toBeVisible()

  for (const label of TABS) {
    await expect(nav.getByRole('button', { name: label, exact: true })).toBeVisible()
  }
})

test('report button is present', async ({ page }) => {
  await page.goto('/')
  // This is how issues get filed. If it disappears, users lose the way to report that
  // anything else disappeared.
  await expect(page.locator('header .report-btn')).toBeVisible()
})

test('tabs actually switch', async ({ page }) => {
  await page.goto('/')
  const nav = page.locator('header nav')

  // Present-but-inert navigation would pass a existence-only check, so click through.
  for (const label of TABS) {
    const button = nav.getByRole('button', { name: label, exact: true })
    await button.click()
    await expect(button).toHaveClass(/active/)
  }
})
