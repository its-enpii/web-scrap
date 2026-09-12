"""Intercept 1 delete UI -> capture endpoint API, lalu reusable."""
import asyncio, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

URL = "https://ai-omni.enpiistudio.com/dashboard/providers/bai"
UPAT = re.compile(r"user_[A-Za-z0-9]{12}")
captured = []

async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        async def on_req(req):
            if req.method in ("POST", "DELETE", "PATCH", "PUT") and "/api" in req.url or req.method in ("POST","DELETE","PATCH","PUT") and ("connection" in req.url or "provider" in req.url):
                body = None
                try:
                    body = req.post_data
                except Exception:
                    pass
                captured.append({"m": req.method, "u": req.url, "b": (body or "")[:300]})
        page.on("request", on_req)
        await B.omni_login(page)
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        txt = await page.evaluate("document.body.innerText")
        users = UPAT.findall(txt)
        # cari node teks, naik sampai ketemu container yang punya TEPAT SATU set tombol row lalu delete
        target = users[0]
        done = await page.evaluate("""(u) => {
            const els = Array.from(document.querySelectorAll('*')).filter(e =>
                e.children.length === 0 && (e.textContent||'').trim() === u);
            if (!els.length) return 'no-text-node';
            for (const el of els) {
                let p = el;
                for (let k = 0; k < 10 && p.parentElement; k++) {
                    p = p.parentElement;
                    const dels = Array.from(p.querySelectorAll(':scope button')).filter(b =>
                        (b.innerText||'').trim() === 'delete');
                    if (dels.length === 1) { p.dataset.probeRow='1'; dels[0].click(); return 'clicked via '+k+' levels'; }
                }
            }
            return 'no-single-delete';
        }""", target)
        print("probe:", done, "target:", target, flush=True)
        await page.wait_for_timeout(2000)
        conf = page.locator("div.fixed.inset-0.z-50 button").filter(
            has_text=re.compile(r"^(Delete|Confirm|Yes|Hapus)$", re.I))
        if await conf.count():
            await conf.first.click(force=True)
            await page.wait_for_timeout(2500)
        print("CAPTURED MUTATIONS:", flush=True)
        for c in captured:
            print("  ", c, flush=True)
        # cek beneran kehapus?
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(5000)
        t2 = await page.evaluate("document.body.innerText")
        print("target masih ada?", target in t2, "| connections:", re.findall(r"\d+ connections", t2), flush=True)
asyncio.run(main())
