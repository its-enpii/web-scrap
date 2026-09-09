"""Enumerasi semua halaman daftar koneksi BAI lalu diff vs 174 userId."""
import asyncio, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

DASH = "https://ai-omni.enpiistudio.com/dashboard/providers/bai"

async def main():
    data = json.load(open('/root/.hermes/cache/documents/doc_71de3df0fc03_bai_174_accounts_1.json'))
    mine = set(a['userId'] for a in data)
    seen = set()
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        await page.goto(DASH, wait_until="load", timeout=30000)
        await page.wait_for_function("() => /user_[A-Za-z0-9]{12}/.test(document.body.innerText)", timeout=30000)
        await page.wait_for_timeout(2000)
        m = re.search(r"(\d+)\s+connections", await page.evaluate("document.body.innerText"))
        header = int(m.group(1))
        npages = int(re.search(r"1\s*/\s*(\d+)", await page.evaluate("document.body.innerText")).group(1))
        print(f"header={header} pages={npages}", flush=True)
        for pg in range(npages):
            txt = await page.evaluate("document.body.innerText")
            got = set(re.findall(r"user_[A-Za-z0-9]{12}", txt))
            seen |= got
            print(f"page {pg+1}: total unik = {len(seen)}", flush=True)
            if pg < npages - 1:
                nxt = page.locator("button:has-text('chevron_right')").first
                await nxt.scroll_into_view_if_needed()
                await nxt.click(force=True)
                await page.wait_for_timeout(2500)
                # pastikan halaman berganti
                cur = re.search(r"(\d+)–(\d+)\s*/\s*\d+", await page.evaluate("document.body.innerText"))
                print("  range sekarang:", cur.group(0) if cur else "?", flush=True)
    missing = sorted(mine - seen)
    matched = len(mine & seen)
    print(f"=== MINE matched di portal: {matched}/{len(mine)} ===", flush=True)
    print(f"=== TIDAK ada: {len(missing)} ===", flush=True)
    for u in missing:
        print("  ", u, flush=True)
    json.dump({"matched": matched, "missing": missing}, open('/root/projects/web-scrap/results/_bai_diff.json','w'))
    extra = sorted(seen - mine)
    print(f"existing lain (bukan batch ini): {len(extra)}", flush=True)

asyncio.run(main())
