"""Dump struktur row daftar: urutan user_ vs tombol delete (index-aligned?)."""
import asyncio, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        await page.goto("https://ai-omni.enpiistudio.com/dashboard/providers/bai", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(6000)
        r = await page.evaluate("""() => {
            const users = Array.from(document.querySelectorAll('*')).filter(e =>
                (e.textContent||'').trim().match(/^user_[A-Za-z0-9]{12}/);
            const dels = Array.from(document.querySelectorAll('button')).filter(b =>
                (b.innerText||'').trim() === 'delete');
            const pair = users.slice(0,5).map(u => {
                let p = u, found = null, levels = -1;
                for (let k = 0; k < 12 && p.parentElement; k++) {
                    p = p.parentElement;
                    const dd = Array.from(p.querySelectorAll('button')).filter(b => (b.innerText||'').trim() === 'delete');
                    if (dd.length) { found = dd.length; levels = k; break; }
                }
                return {t: u.textContent.trim().slice(0,20), child: u.children.length, btnsInNearestContainer: found, levels, cls: u.parentElement.className.slice(0,50)};
            });
            // hitung delete dalam container user pertama
            return {users: users.length, dels: dels.length, pair,
                firstUserParentChain: (() => { let p = users[0], ch = []; for (let k=0;k<6&&p;k++){ch.push(p.tagName+'.'+(p.className||'').toString().slice(0,40)); p=p.parentElement;} return ch; })()};
        }""")
        print("users:", r["users"], "dels:", r["dels"], flush=True)
        for x in r["pair"]:
            print(x, flush=True)
        for c in r["firstUserParentChain"]:
            print("  ", c, flush=True)
asyncio.run(main())
