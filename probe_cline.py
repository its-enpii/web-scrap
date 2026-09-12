"""Probe halaman provider cline: dump teks halaman + isi modal Add.
Baca-only: tidak klik Connect, tidak submit apa pun."""
import asyncio, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

CLINE_URL = "https://ai-omni.enpiistudio.com/dashboard/providers/cline"
RES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True,
                             proxy={"server": "socks5://127.0.0.1:1080",
                                    "bypass": "localhost 127.0.0.1 .enpiistudio.com"}) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        await page.goto(CLINE_URL, wait_until="load", timeout=45000)
        await page.wait_for_timeout(6000)
        txt = await page.evaluate("document.body.innerText")
        open(f"{RES}/_cline_page.txt", "w").write(txt)
        await page.screenshot(path=f"{RES}/_cline_page.png", full_page=True)
        print("==== PAGE TEXT (first 3000) ====", flush=True)
        print(txt[:3000], flush=True)

        btns = await page.evaluate("""() => Array.from(document.querySelectorAll('button,a'))
            .map(b=>({t:(b.innerText||'').replace(/\\s+/g,' ').trim().slice(0,50), tag:b.tagName}))
            .filter(x=>x.t)""")
        print("==== BUTTONS/LINKS ====", flush=True)
        seen = set()
        for b in btns:
            k = (b['t'], b['tag'])
            if k in seen:
                continue
            seen.add(k)
            print(b['tag'], "|", b['t'], flush=True)

        # coba buka modal Add (read-only, tanpa submit)
        add = page.locator("button:has-text('Add'), button:has-text('Tambahkan')").first
        try:
            await add.click(timeout=10000)
        except Exception:
            try:
                await add.evaluate("el => el.click()")
            except Exception as e:
                print("[!] tombol Add tidak ketemu:", e, flush=True)
                return
        await page.wait_for_timeout(3000)
        warn = page.locator("button:has-text('I understand, continue')").first
        if await warn.count():
            try:
                await warn.click(timeout=8000)
            except Exception:
                await warn.evaluate("el => el.click()")
            await page.wait_for_timeout(3000)
        modal = page.locator("div.fixed.inset-0.z-50")
        if await modal.count():
            mtxt = await modal.first.inner_text()
            open(f"{RES}/_cline_modal.txt", "w").write(mtxt)
            print("==== MODAL TEXT (first 4000) ====", flush=True)
            print(mtxt[:4000], flush=True)
            vals = await modal.locator("input").evaluate_all("els => els.map(e=>({v:(e.value||'').slice(0,200), ph:e.placeholder||''}))")
            print("==== MODAL INPUTS ====", flush=True)
            for v in vals:
                print(v, flush=True)
            tabs = await modal.locator("button").evaluate_all("els => els.map(e=>(e.innerText||'').replace(/\\s+/g,' ').trim()).filter(Boolean)")
            print("==== MODAL BUTTONS ====", flush=True)
            print(tabs, flush=True)
        else:
            print("[!] modal tidak terdeteksi selector div.fixed.inset-0.z-50", flush=True)
            body = await page.evaluate("document.body.innerText")
            print("==== AFTER-CLICK BODY ====", flush=True)
            print(body[:4000], flush=True)
        await page.screenshot(path=f"{RES}/_cline_modal.png", full_page=True)

asyncio.run(main())
