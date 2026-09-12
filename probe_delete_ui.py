"""Probe UI hapus koneksi per-baris & bulk di halaman provider bai."""
import asyncio, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        await page.goto("https://ai-omni.enpiistudio.com/dashboard/providers/bai", wait_until="load", timeout=30000)
        await page.wait_for_function("() => /user_[A-Za-z0-9]{12}/.test(document.body.innerText)", timeout=30000)
        await page.wait_for_timeout(2000)
        # checkbox per baris?
        cb = await page.locator("input[type='checkbox']").count()
        print("checkboxes:", cb, flush=True)
        # hover baris pertama -> tombol aksi
        row = page.locator("text=user_AMG4GfEGp0Iu").first
        try:
            await row.hover(timeout=8000)
        except Exception:
            pass
        await page.wait_for_timeout(1200)
        btns = await page.evaluate("""() => Array.from(document.querySelectorAll('button')).map(b=>({
            t:(b.innerText||'').replace(/\\s+/g,' ').slice(0,25), aria:b.getAttribute('aria-label')}))""")
        interesting = [b for b in btns if b['aria'] and any(k in b['aria'].lower() for k in ('delete','remove','trash'))] + \
                      [b for b in btns if 'delete' in b['t'].lower() or 'trash' in b['t'].lower() or 'remove' in b['t'].lower()]
        print("delete-ish buttons:", interesting[:10], flush=True)
        allar = sorted(set(b['aria'] for b in btns if b['aria']))
        print("all aria labels:", allar, flush=True)
        # tombol 'select all'?
        sa = [b for b in btns if 'select' in b['t'].lower() or (b['aria'] and 'select' in b['aria'].lower())]
        print("select buttons:", sa, flush=True)
asyncio.run(main())
