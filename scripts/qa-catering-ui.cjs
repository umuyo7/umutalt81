// Yerel, sentetik test HTML'lerini bağımsız headless tarayıcıda doğrular.
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.QA_BROWSER});
  try {
    const root = path.resolve(__dirname,'..');
    const folder = path.join(root,'tmp','pdfs');
    for (const width of [1440,390]) {
      for (const name of ['index','musteriler','gunluk_giris','taziye_ekle','calisanlar','giderler','raporlama']) {
        const page = await browser.newPage({viewport:{width,height:1000}});
        let html = fs.readFileSync(path.join(folder,name+'.html'),'utf8');
        html = html.replace(/<link rel="stylesheet"[^>]+>/,'<style>'+fs.readFileSync(path.join(root,'app','static','app.css'),'utf8')+'</style>');
        await page.setContent(html);
        const overflow = await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
        if (overflow) throw new Error(`Yatay sayfa taşması: ${name} ${width}`);
        if (name==='musteriler') {
          await page.locator('[data-search]').fill('bulunmayacakfirma');
          const visible = await page.locator('[data-row]').evaluateAll(rows=>rows.filter(row=>!row.hidden).length);
          if(visible) throw new Error('Arama filtresi çalışmıyor');
          await page.locator('[data-search]').fill('');
        }
        if (['index','musteriler','gunluk_giris','raporlama'].includes(name)) {
          await page.screenshot({path:path.join(folder,`${name}-${width}.png`),fullPage:true});
        }
        await page.close();
      }
    }
    console.log('catering-ui-desktop-mobile-ok');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
