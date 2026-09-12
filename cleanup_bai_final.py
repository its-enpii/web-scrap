"""Tuntaskan cleanup default 'bai': hapus semua user_* (sisakan grmill), lalu verifikasi."""
import asyncio, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from camoufox.async_api import AsyncCamoufox
import bulk_add_to_omni as B

URL = "https://ai-omni.enpiistudio.com/dashboard/providers/bai"
UPAT = re.compile(r"user_[A-Za-z0-9]{12}")


def conn_count(txt):
    m = re.search(r"(\d+)\s+connections", txt)
    return int(m.group(1)) if m else None


async def safe_goto(page):
    try:
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
    except Exception:
        await page.wait_for_timeout(3000)
        try:
            await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass
    await page.wait_for_timeout(4000)


async def delete_row(page, user):
    """Scroll row ke tengah, klik tombol delete milik row itu, konfirmasi."""
    # locate node teks persis
    el = page.locator(f"text='{user}'").last
    try:
        await el.scroll_into_view_if_needed(timeout=8000)
    except Exception:
        pass
    await page.wait_for_timeout(700)
    ok = await page.evaluate("""(u) => {
        const els = Array.from(document.querySelectorAll('*')).filter(e =>
            e.children.length === 0 && (e.textContent||'').trim() === u);
        for (const el of els) {
            let p = el;
            for (let k = 0; k < 9 && p.parentElement; k++) {
                p = p.parentElement;
                if ((p.className||'').toString().includes('rounded') || p.querySelectorAll('button').length >= 3) {
                    const dels = Array.from(p.querySelectorAll('button')).filter(b =>
                        (b.innerText||'').trim() === 'delete');
                    if (dels.length >= 1) {
                        dels[0].scrollIntoView({block:'center'});
                        dels[0].click();
                        return true;
                    }
                }
            }
        }
        return false;
    }""", user)
    if not ok:
        return False
    await page.wait_for_timeout(1300)
    conf = page.locator("div.fixed.inset-0.z-50 button").filter(
        has_text=re.compile(r"^(Delete|Confirm|Yes|Hapus)$", re.I))
    if await conf.count():
        await conf.first.click(force=True)
        await page.wait_for_timeout(1300)
    return True


async def main():
    gone_confirmed = 0
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        print("[+] login ok", flush=True)
        await safe_goto(page)
        failed = set()
        removed = 0
        while True:
            txt = await page.evaluate("document.body.innerText")
            users = [u for u in UPAT.findall(txt) if u not in failed]
            if not users:
                # reload sekali untuk memastikan bukan habis halaman
                await safe_goto(page)
                txt = await page.evaluate("document.body.innerText")
                users = [u for u in UPAT.findall(txt) if u not in failed]
                if not users:
                    break
            target = users[0]
            ok = await delete_row(page, target)
            if not ok:
                failed.add(target)
                print(f"[!] gagal locate delete: {target} (total gagal {len(failed)})", flush=True)
                if len(failed) >= 8:
                    break
                await safe_goto(page)
                continue
            removed += 1
            if removed % 20 == 0:
                print(f"[+] removed {removed} — connections: "
                      f"{conn_count(await page.evaluate('document.body.innerText'))}", flush=True)
                await safe_goto(page)
        # rekap
        await safe_goto(page)
        txt = await page.evaluate("document.body.innerText")
        left = set(UPAT.findall(txt))
        print(f"[i] removed total: {removed} | gagal locate: {sorted(failed)}", flush=True)
        print(f"[V] bai SESUDAH: connections={conn_count(txt)} user_ di hal1={len(left)}", flush=True)
        # enumerate semua halaman utk memastikan nol user_
        m = re.search(r"(\d+)\s+accounts", txt)
        total = int(m.group(1)) if m else conn_count(txt) or 0
        npages = max(1, -(-total // 50))
        allu = set(left)
        for pg in range(npages - 1):
            nxt = page.locator("button:has-text('chevron_right')").first
            try:
                await nxt.scroll_into_view_if_needed()
                await nxt.click(force=True)
                await page.wait_for_timeout(2500)
            except Exception:
                break
            allu |= set(UPAT.findall(await page.evaluate("document.body.innerText")))
        print(f"[V] SISA user_ di seluruh halaman bai: {len(allu)}", flush=True)
        if allu:
            print("   ", sorted(allu)[:20], flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_bai_clean_final.png", full_page=True)


if __name__ == "__main__":
    asyncio.run(main())
