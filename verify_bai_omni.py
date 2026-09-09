"""Verifikasi akhir: connection count + keberadaan user chunk terakhir di dashboard BAI."""
import asyncio, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

DASH = "https://ai-omni.enpiistudio.com/dashboard/providers/bai"

async def main():
    data = json.load(open('/root/.hermes/cache/documents/doc_71de3df0fc03_bai_174_accounts_1.json'))
    tail_users = [a['userId'] for a in data[-10:]]
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        await page.goto(DASH, wait_until="load", timeout=30000)
        await page.wait_for_function("() => /user_[A-Za-z0-9]{12}/.test(document.body.innerText) || /connections/.test(document.body.innerText)", timeout=30000)
        await page.wait_for_timeout(3000)
        # pakai search/filter bawaan kalau ada
        hit = {}
        box = page.locator("input[type='search'], input[placeholder*='Search'], input[placeholder*='cari'], input[placeholder*='filter']")
        has_box = await box.count()
        print("search box found:", has_box, flush=True)
        for u in tail_users:
            if has_box:
                await box.first.fill(u)
                await page.wait_for_timeout(1500)
                txt = await page.evaluate("document.body.innerText")
                hit[u] = u in txt
                await box.first.fill("")
                await page.wait_for_timeout(500)
            else:
                txt = await page.evaluate("document.body.innerText")
                hit[u] = u in txt
        print("tail-10 users terlihat:", sum(hit.values()), "dari 10", flush=True)
        for u, ok in hit.items():
            print(("  OK " if ok else "  MISS ") + u, flush=True)
        txt = await page.evaluate("document.body.innerText")
        m = re.search(r"(\d+)\s+connections", txt)
        print("header connections:", m.group(1) if m else "n/a", flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_bai_verify.png", full_page=True)

asyncio.run(main())
