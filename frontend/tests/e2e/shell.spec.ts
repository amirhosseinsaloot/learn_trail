import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

const routes = [
  { path: '/', heading: 'Conversations' },
  { path: '/c/new', heading: 'New conversation' },
  { path: '/c/0193b6c4-3f1a-7c2e-9d6e-1a2b3c4d5e6f', heading: 'Conversation' },
  { path: '/c/0193b6c4-3f1a-7c2e-9d6e-1a2b3c4d5e6f/summary', heading: 'Review before saving' },
  { path: '/library', heading: 'Library' },
  { path: '/library/0193b6c4-3f1a-7c2e-9d6e-1a2b3c4d5e6f', heading: 'Saved summary' },
  { path: '/ask', heading: 'Ask my knowledge' },
  { path: '/account', heading: 'Account' },
  { path: '/login', heading: 'Sign in' },
  { path: '/register', heading: 'Create your account' },
];

async function focusedName(page: Page): Promise<string> {
  return page.evaluate(() => {
    const element = document.activeElement;
    if (!(element instanceof HTMLElement)) return '';
    return (element.getAttribute('aria-label') ?? element.textContent ?? '').trim();
  });
}

test.describe('application shell', () => {
  test('exposes landmarks and the skip link is the first focusable element', async ({
    page,
  }, testInfo) => {
    await page.goto('/');
    await expect(page.getByRole('banner')).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Main' })).toBeVisible();
    await expect(page.getByRole('main')).toBeVisible();
    await page.keyboard.press('Tab');
    await expect(page.getByRole('link', { name: 'Skip to main content' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.locator('#main')).toBeFocused();
    await page.screenshot({ path: testInfo.outputPath('shell.png'), fullPage: true });
  });

  for (const route of routes) {
    test(`${route.path} renders its h1 and passes axe`, async ({ page }) => {
      await page.goto(route.path);
      const headings = page.getByRole('heading', { level: 1 });
      await expect(headings).toHaveCount(1);
      await expect(headings).toHaveText(route.heading);
      const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
      expect(results.violations).toEqual([]);
    });
  }

  test('keyboard reaches every navigation control in reading order', async ({ page }) => {
    await page.goto('/ask');
    const reached: string[] = [];
    for (let step = 0; step < 8; step += 1) {
      await page.keyboard.press('Tab');
      reached.push(await focusedName(page));
    }
    expect(reached[0]).toBe('Skip to main content');
    expect(reached).toEqual(expect.arrayContaining(['Library', 'Ask', 'Account']));
    expect(reached.some((name) => name === 'Conversations' || name === 'Chats')).toBe(true);
  });

  test('a route change moves focus to the new h1', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('link', { name: 'Library' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Library' })).toBeFocused();
  });

  test('an unknown route shows Not found with a link home', async ({ page }) => {
    await page.goto('/nowhere');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Not found');
    await page.getByRole('link', { name: 'Go to your conversations' }).click();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Conversations');
  });

  test('has no horizontal scroll at 320px effective width', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 700 });
    await page.goto('/c/0193b6c4-3f1a-7c2e-9d6e-1a2b3c4d5e6f/summary');
    const overflow = await page.evaluate(() => {
      const root = document.documentElement;
      return root.scrollWidth - root.clientWidth;
    });
    expect(overflow).toBeLessThanOrEqual(0);
  });
});
