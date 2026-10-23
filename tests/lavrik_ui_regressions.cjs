// Isolated UI regression checks. No app import, credentials or user database.
// Usage: node tests/lavrik_ui_regressions.cjs (requires Playwright).
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const read = name => fs.readFileSync(path.join(root, name), 'utf8');
const styles = text => [...text.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)]
  .map(match => match[1]).join('\n');
const globalCss = ['style.css', 'css/nav.css', 'css/mobile.css',
  'css/mobile_features.css', 'css/errors.css', 'css/formyla_dark.css']
  .map(name => read(`static/${name}`)).join('\n');

async function run(browser) {
  const results = [];
  for (const width of [1280, 375]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const fixture = async (css, html) => page.setContent(
      `<html lang="ru"><head><meta name="viewport" content="width=device-width">
       <style>${globalCss}\n${css}</style></head><body>${html}</body></html>`);

    const chat = read('templates/chat.html');
    await fixture(styles(chat), '<button id="openGroup">Новая группа</button>');
    await page.evaluate(chat.slice(chat.indexOf('let _gcSelected ='),
      chat.indexOf('async function submitGroupCreate()')) + `
      function escHtml(s) { return s.replace(/</g, '&lt;'); }
      window.fetch = async () => ({ok:true,json:async()=>({conversations:[
        {friend:{id:1,name:'Тестовый участник'}}]})});
      document.getElementById('openGroup').onclick = openGroupCreateModal;
    `);
    await page.locator('#openGroup').click();
    await page.locator('.gc-friend-row').click();
    assert.equal(await page.locator('#gcPickedCount').textContent(), '1');
    const group = await page.evaluate(() => {
      const rect = sel => document.querySelector(sel).getBoundingClientRect();
      const card = rect('.gc-create-card'), head = rect('.gc-create-head');
      const icon = rect('.gc-create-icon'), close = rect('.gc-create-close');
      const input = rect('#gcNameInput');
      return { inset: icon.left-card.left, centerOffset:
        close.top+close.height/2-(head.top+head.height/2),
        fits: card.right<=innerWidth && close.right<=card.right,
        inputInset:card.right-input.right,
        scrollLeft:document.querySelector('.gc-create-card').scrollLeft };
    });
    assert(group.inset >= 20, JSON.stringify(group));
    assert(Math.abs(group.centerOffset) <= 4, JSON.stringify(group));
    assert(group.fits, 'Group dialog overflows viewport');
    assert(group.inputInset >= 20, 'Group input overflows side margin');
    assert.equal(group.scrollLeft, 0, 'Autofocus scrolls the dialog horizontally');
    await page.locator('.gc-create-close').click();
    assert(await page.locator('#gcCreateModal').evaluate(el => el.hidden));
    assert(!(await page.locator('#gcCreateModal').isVisible()));
    await page.locator('#openGroup').click();
    assert.equal(await page.locator('#gcPickedCount').textContent(), '0');
    await page.getByRole('button', {name:'Отмена',exact:true}).click();
    assert(!(await page.locator('#gcCreateModal').isVisible()));

    const daily = read('templates/daily_tasks/daily_tasks_dashboard.html');
    const debtButton = daily.match(/<button type="button" class="dt-debt-toggle-btn"[\s\S]*?<\/button>/)[0]
      .replace('{{ data.debt.total }}', '123456');
    await fixture(styles(daily), `<div class="dt-debt-block">${debtButton}
      <div id="dt-debt-body" class="dt-debt-body dt-hidden">Задачи</div></div>`);
    await page.evaluate(daily.match(/window\.toggleDebt = function\(\) \{[\s\S]*?\n  \};/)[0]);
    const inset = await page.evaluate(() => {
      const button = document.querySelector('#dt-debt-toggle').getBoundingClientRect();
      const arrow = document.querySelector('#dt-debt-toggle-arrow').getBoundingClientRect();
      return button.right-arrow.right;
    });
    assert(inset >= 12, `Debt arrow inset ${inset}`);
    await page.locator('#dt-debt-toggle').click();
    assert(!(await page.locator('#dt-debt-body').getAttribute('class')).includes('dt-hidden'));
    await page.locator('#dt-debt-toggle').click();
    assert((await page.locator('#dt-debt-body').getAttribute('class')).includes('dt-hidden'));

    const notices = read('templates/admin/notices.html');
    await fixture(styles(notices), notices.match(/<div class="ntc-senders">[\s\S]*?<\/div>/)[0]);
    for (const value of ['curator', 'support']) {
      const radio = page.locator(`input[value="${value}"]`);
      await radio.check();
      assert(await radio.isChecked());
      const appearance = await radio.evaluate(el => {
        const s = getComputedStyle(el);
        return { width:s.width, background:s.backgroundColor, shadow:s.boxShadow };
      });
      assert.equal(appearance.width, '18px');
      assert.equal(appearance.background, 'rgba(0, 0, 0, 0)');
      assert.equal(appearance.shadow, 'none');
    }
    await page.keyboard.press('Tab');
    await page.keyboard.press('Shift+Tab');
    assert.equal(await page.locator('input:focus-visible').count(), 1);
    assert.deepEqual(errors, []);
    results.push({ width, group, debtArrowInset:inset, consoleErrors:errors.length });
    await page.close();
  }
  const uid = '64ee049250bb71f470ce508dca5ba72b807fe82b83f4b95a6d284d19192408bb';
  const task = JSON.parse(read('data/olymp_catalog/vsosh.json')).find(t => t.uid === uid);
  assert(task.text.includes('\\(11 \\times 11\\)'));
  assert(task.text.includes('144 вершины'));
  assert.equal(task.fig_statement.length, 1);
  const svg = read(`static/olymp_figures/${task.fig_statement[0]}`);
  assert(svg.includes('width="264" height="264"')); // 11 cells of 24px.
  assert(svg.includes('width="288" height="288"')); // 12 dots per axis.
  assert(svg.includes('width="24" height="24"'));
  return results;
}
module.exports = { run };
if (require.main === module) {
  (async () => {
    const { chromium } = require('playwright');
    const browser = await chromium.launch({headless:true,channel:'chromium'});
    try { console.log(JSON.stringify(await run(browser), null, 2)); }
    finally { await browser.close(); }
  })().catch(error => { console.error(error); process.exitCode = 1; });
}
