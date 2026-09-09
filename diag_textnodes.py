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
        txt = await page.evaluate("document.body.innerText")
        users = re.findall(r"user_[A-Za-z0-9]{12}", txt)
        print("users in body:", len(users), users[:3], flush=True)
        r = await page.evaluate("""() => {
            const out = {exact:[], substr:[], textnodes:0};
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let n;
            while ((n = walker.nextNode())) {
                const t = (n.textContent||'').trim();
                if (/^user_[A-Za-z0-9]{12}$/.test(t)) { out.exact.push(t); }
                else if (t.includes('user_')) { out.substr.push(JSON.stringify(t).slice(0,60)); }
                out.textnodes++;
            }
            return out;
        }""")
        print("text nodes scanned:", r["textnodes"], flush=True)
        print("exact matches:", len(r["exact"]), r["exact"][:5], flush=True)
        print("substr oddities:", r["substr"][:10], flush=True)
asyncio.run(main())
