"""Cleanup final default 'bai': hapus semua koneksi user_* (3 grmill tetap),
dengan intercept API delete utk fallback cepat, lalu verifikasi."""
import asyncio, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

BASE = "https://ai-omni.enpiistudio.com/dashboard/providers"
UPAT = re.compile(r"user_[A-Za-z0-9]{12}")
api_delete = []


def conn_count(txt):
    m = re.search(r"(\d+)\s+connections", txt)
    return int(m.group(1)) if m else None


async def safe_goto(page, slug):
    for _ in range(2):
        try:
            await page.goto(f"{BASE}/{slug}", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(4500)
            return
        except Exception:
            await page.wait_for_timeout(3000)


async def visible_users(page):
    return UPAT.findall(await page.evaluate("document.body.innerText"))


async def click_delete_for(page, user):
    """Klik delete milik baris `user` (bukan sekadar row pertama yang visible)."""
    return await page.evaluate("""(u) => {
        const els = Array.from(document.querySelectorAll('*')).filter(e =>
            !e.children.length && (e.textContent||'').trim() === u);
        for (const el of els) {
            el.scrollIntoView({block:'center'});
            let p = el, best = null;
            for (let k = 0; k < 12 && p.parentElement; k++) {
                p = p.parentElement;
                const dels = Array.from(p.querySelectorAll('button')).filter(b =>
                    (b.innerText||'').trim() === 'delete');
                if (dels.length === 1) { dels[0].click(); return true; }
                if (dels.length > 1) {
                    // ambil tombol terdekat vertikal dgn node user
                    const uy = el.getBoundingClientRect().y;
                    let near = null, nd = 1e9;
                    for (const d of dels) { const dy = Math.abs(d.getBoundingClientRect().y - uy);
                        if (dy < nd) { nd = dy; near = d; } }
                    if (near && nd < 160) { near.click(); return true; }
                    break;
                }
            }
        }
        return false;
    }""", user)


async def confirm_modal(page):
    conf = page.locator("div.fixed.inset-0.z-50 button").filter(
        has_text=re.compile(r"^(Delete|Confirm|Yes|Hapus)$", re.I))
    if await conf.count():
        await conf.first.click(force=True)
        await page.wait_for_timeout(1200)
        return True
    return False


async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()

        async def on_req(req):
            if req.method in ("DELETE", "POST", "PATCH") and "/api/" in req.url and "auth" not in req.url:
                api_delete.append({"m": req.method, "u": req.url, "b": (req.post_data or "")[:200]})
        page.on("request", on_req)

        await B.omni_login(page)
        print("[+] login ok", flush=True)
        await safe_goto(page, "bai")
        print("[i] bai connections:", conn_count(await page.evaluate("document.body.innerText")), flush=True)

        removed = stuck = 0
        batch = 1
        while batch <= 30:
            batch += 1
            users = await visible_users(page)
            if not users:
                await safe_goto(page, "bai")
                users = await visible_users(page)
                if not users:
                    break
            # hapus dari baris paling bawah halaman 1 (indeks DOM aman)
            target = users[-1]
            ok = await click_delete_for(page, target)
            if not ok:
                stuck += 1
                print(f"[!] tak bisa klik delete: {target} (stuck {stuck})", flush=True)
                if stuck > 6:
                    break
                await safe_goto(page, "bai")
                continue
            await page.wait_for_timeout(1200)
            await confirm_modal(page)
            removed += 1
            stuck = 0
            if removed % 25 == 0:
                await safe_goto(page, "bai")
                print(f"[+] removed {removed} — connections: "
                      f"{conn_count(await page.evaluate('document.body.innerText'))}", flush=True)

        await safe_goto(page, "bai")
        txt = await page.evaluate("document.body.innerText")
        left = set(UPAT.findall(txt))
        print(f"[V] bai: connections={conn_count(txt)} | removed={removed} | user_ hal1={len(left)}", flush=True)
        print("API delete pattern:", json.dumps(api_delete[:5], indent=1), flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_bai_clean_v2.png", full_page=True)


if __name__ == "__main__":
    asyncio.run(main())
