"""Cleanup bai v4: delete by Y-ALIGNMENT row + force click + JS fallback.

Diagnosa v3: JS strict-text-match gagal find node utk row tertentu. v4 pakai
Playwright locator 'has-text' (substring) utk locate, bounding box utk pass
vertikal, lalu klik tombol delete terdekat sebaris (force). Fallback: JS
textContent match (bukan innerText).
"""
import asyncio, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

BASE = "https://ai-omni.enpiistudio.com/dashboard/providers"
UPAT = re.compile(r"user_[A-Za-z0-9]{12}")


def conn_count(txt):
    m = re.search(r"(\d+)\s+connections", txt)
    return int(m.group(1)) if m else None


async def safe_goto(page, slug):
    for _ in range(2):
        try:
            await page.goto(f"{BASE}/{slug}", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
            return
        except Exception:
            await page.wait_for_timeout(3000)


async def delete_row(page, user):
    row = page.locator(f"div:has-text('{user}')").filter(
        has=page.locator("button:text-content-is('delete')")).last
    try:
        ub = await row.bounding_box(timeout=8000)
    except Exception:
        ub = None
    if not ub:
        # fallback JS: locate leaf by textContent, klik delete sebaris
        ok = await page.evaluate("""(u) => {
            const els = Array.from(document.querySelectorAll('*')).filter(e =>
                (e.textContent||'').trim().startsWith(u + ' ') || (e.textContent||'').trim() === u);
            if (!els.length) return 'no-node';
            const el = els[els.length-1];
            el.scrollIntoView({block:'center'});
            const uy = el.getBoundingClientRect().y;
            let best=null, bd=1e9;
            for (const b of document.querySelectorAll('button')) {
                if ((b.textContent||'').trim() !== 'delete') continue;
                const d = Math.abs(b.getBoundingClientRect().y - uy);
                if (d < bd) { bd = d; best = b; }
            }
            if (best && bd < 120) { best.click(); return 'clicked-js '+bd; }
            return 'no-btn ' + (best?bd:'none');
        }""", user)
        print(f"    js-fallback {user}: {ok}", flush=True)
        if not ok.startswith("clicked"):
            return False
    else:
        btn = row.locator("button:text-content-is('delete')").last
        bb = await btn.bounding_box()
        try:
            await btn.scroll_into_view_if_needed(timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(400)
        try:
            await btn.click(timeout=8000)
        except Exception:
            try:
                await btn.click(force=True, timeout=8000)
            except Exception:
                print(f"    click gagal {user} bb={bb}", flush=True)
                return False
    await page.wait_for_timeout(1300)
    conf = page.locator("div.fixed.inset-0.z-50 button").filter(
        has_text=re.compile(r"^(Delete|Confirm|Yes|Hapus)$", re.I))
    if await conf.count():
        await conf.first.click(force=True)
        await page.wait_for_timeout(1300)
    return True


async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        print("[+] login ok", flush=True)
        await safe_goto(page, "bai")
        removed = 0
        failed = set()
        while True:
            txt = await page.evaluate("document.body.innerText")
            users = [u for u in UPAT.findall(txt) if u not in failed]
            if not users:
                await safe_goto(page, "bai")
                txt = await page.evaluate("document.body.innerText")
                users = [u for u in UPAT.findall(txt) if u not in failed]
                if not users:
                    break
            target = users[-1]
            ok = await delete_row(page, target)
            if not ok:
                failed.add(target)
                print(f"[!] skip permanen {target} (gagal {len(failed)})", flush=True)
                if len(failed) >= 10 and removed == 0:
                    print("[!] terlalu banyak gagal tanpa sukses — berhenti", flush=True)
                    break
                await safe_goto(page, "bai")
                continue
            removed += 1
            if removed % 20 == 0:
                print(f"[+] removed {removed} — connections: "
                      f"{conn_count(await page.evaluate('document.body.innerText'))}", flush=True)
                await safe_goto(page, "bai")
        await safe_goto(page, "bai")
        txt = await page.evaluate("document.body.innerText")
        print(f"[V] bai FINAL: connections={conn_count(txt)} user_={len(set(UPAT.findall(txt)))} "
              f"removed={removed} skipped={sorted(failed)}", flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_bai_clean_v4.png", full_page=True)


if __name__ == "__main__":
    asyncio.run(main())
