// Isolated contact-form test; all requests are mocked, no user data is read.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
async function run(browser) {
  const about = read('templates/about.html');
  const css = ['style.css','css/nav.css','css/mobile.css','css/mobile_features.css',
    'css/errors.css','css/formyla_dark.css'].map(n => read(`static/${n}`)).join('\n');
  const aboutStyles = [...about.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)]
    .map(m => m[1]).join('\n');
  const contact = about.match(/<section class="about-section support-section"[\s\S]*?<\/section>/)[0];
  const script = about.match(/\(function initContactChat\(\) \{[\s\S]*?\n\}\)\(\);/)[0]
    .replace(/const IS_AUTH = .*?;/, 'const IS_AUTH = false;')
    .replace(/const USER_DISPLAY = .*?;/, 'const USER_DISPLAY = "Тест";');
  const results = [];
  for (const width of [320,375,430,1280]) {
    const page = await browser.newPage({viewport:{width,height:1000}});
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.setContent(`<style>${css}\n${aboutStyles}</style><div class="about2">${contact}</div>`);
    await page.evaluate(() => {
      window.testRequests = [];
      window.testFailure = false;
      window.fetch = async (url, options) => {
        window.testRequests.push({url, values:[...options.body.entries()]
          .map(([key,value]) => [key, typeof value === 'string' ? value : value.name])});
        return {ok:!window.testFailure,json:async()=>window.testFailure ?
          {ok:false,error:'Тестовая ошибка'} : {ok:true}};
      };
    });
    await page.evaluate(script);
    const geometry = await page.evaluate(() => {
      const rect = s => document.querySelector(s).getBoundingClientRect();
      const avatar=rect('.contact-chat__avatar'), send=rect('#contact-chat-send'),
        attach=rect('#contact-chat-attach'), text=rect('#contact-chat-text'),
        row=rect('.contact-chat__input-row');
      return {avatar:[avatar.width,avatar.height],send:[send.width,send.height],
        textWidth:text.width, textHeight:text.height,
        fits:attach.left>=row.left && text.left>=attach.right &&
          text.right<=send.left && send.right<=row.right && row.right<=innerWidth};
    });
    assert.equal(geometry.avatar[0], geometry.avatar[1]);
    assert.deepEqual(geometry.send,[44,44]);
    assert(geometry.textWidth>=60 && geometry.fits,JSON.stringify({width,...geometry}));
    assert(geometry.textHeight>=64,'Textarea is vertically cramped');
    assert.equal(await page.locator('.contact-chat__avatar svg, .contact-chat__btn svg').count(),3);
    await page.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
    assert.equal(await page.evaluate(()=>window.testRequests.length),0);
    assert(await page.getByText('Напишите сообщение или прикрепите файл',{exact:true}).isVisible());
    await page.getByRole('button',{name:'Баг',exact:true}).click();
    await page.locator('#contact-chat-email').fill('test@example.invalid');
    await page.locator('#contact-chat-text').fill('Тестовое сообщение');
    await page.locator('#contact-chat-fileinput').setInputFiles({
      name:'test.txt',mimeType:'text/plain',buffer:Buffer.from('local fixture')});
    assert.equal(await page.locator('.contact-chat__file-chip').count(),1);
    await page.locator('.contact-chat__file-chip button').click();
    assert.equal(await page.locator('.contact-chat__file-chip').count(),0);
    await page.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('#contact-chat-text').value==='');
    const request = await page.evaluate(()=>window.testRequests[0]);
    assert.equal(request.url,'/api/support');
    assert(request.values.some(([k,v])=>k==='category' && v==='bug'));
    assert(request.values.some(([k,v])=>k==='message' && v==='Тестовое сообщение'));
    await page.locator('#contact-chat-text').fill('Проверка клавиатуры');
    await page.locator('#contact-chat-text').press('Control+Enter');
    await page.waitForFunction(()=>window.testRequests.length===2);
    await page.evaluate(()=>{window.testFailure=true;});
    await page.locator('#contact-chat-text').fill('Проверка ошибки');
    await page.getByRole('button',{name:'Отправить сообщение',exact:true}).click();
    await page.getByText('❌ Тестовая ошибка',{exact:true}).waitFor();
    assert(await page.locator('#contact-chat-send').isEnabled());
    assert.deepEqual(errors,[]);
    results.push({width,...geometry,consoleErrors:errors.length});
    await page.close();
  }
  return results;
}
module.exports={run};
if(require.main===module)(async()=>{
  const {chromium}=require('playwright');
  const browser=await chromium.launch({headless:true,channel:'chromium'});
  try{console.log(JSON.stringify(await run(browser),null,2));}
  finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
