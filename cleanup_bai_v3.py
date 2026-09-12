"""Cleanup final default 'bai' — reuse pola delete yang terbukti (migrate_bai_finish)."""
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
            await page.wait_for_timeout(4500)
            return
        except Exception:
            await page.wait_for_timeout(3000)


async def main():
    async with AsyncCamoufox(headless=True, geoip=False, humanize=True) as browser:
        page = await browser.new_page()
        await B.omni_login(page)
        print("[+] login ok", flush=True)
        await safe_goto(page, "bai")
        removed = 0
        stuck = 0
        while True:
            txt = await page.evaluate("document.body.innerText")
            users = UPAT.findall(txt)
            if not users:
                await safe_goto(page, "bai")
                users = UPAT.findall(await page.evaluate("document.body.innerText"))
                if not users:
                    break
            target = users[-1]
            ok = False
            for cand in reversed(users):
                ok = await page.evaluate("""(u) => {
                    const els = Array.from(document.querySelectorAll('*')).filter(e =>
                        e.children.length === 0 && (e.textContent||'').trim() === u);
                    for (const el of els) {
                        let p = el;
                        for (let k = 0; k < 8 && p.parentElement; k++) {
                            p = p.parentElement;
                            const dels = Array.from(p.querySelectorAll('button')).filter(b =>
                                (b.innerText||'').trim() === 'delete');
                            if (dels.length >= 1) { dels[0].click(); return true; }
                        }
                    }
                    return false;
                }""", cand)
                if ok:
                    target = cand
                    break
            if not ok:
                stuck += 1
                print(f"[!] klik gagal {target} (stuck {stuck})", flush=True)
                await safe_goto(page, "bai")
                if stuck > 6:
                    print("[!] berhenti: 6x stuck beruntun", flush=True)
                    break
                continue
            await page.wait_for_timeout(1200)
            conf = page.locator("div.fixed.inset-0.z-50 button").filter(
                has_text=re.compile(r"^(Delete|Confirm|Yes|Hapus)$", re.I))
            if await conf.count():
                await conf.first.click(force=True)
                await page.wait_for_timeout(1200)
            removed += 1
            stuck = 0
            if removed % 25 == 0:
                print(f"[+] removed {removed} — connections: "
                      f"{conn_count(await page.evaluate('document.body.innerText'))}", flush=True)
                await safe_goto(page, "bai")
        await safe_goto(page, "bai")
        txt = await page.evaluate("document.body.innerText")
        print(f"[V] bai FINAL: connections={conn_count(txt)} | user_ hal1={len(set(UPAT.findall(txt)))} "
              f"| removed sesi ini={removed}", flush=True)
        await page.screenshot(path="/root/projects/web-scrap/results/_bai_clean_final2.png", full_page=True)


if __name__ == "__main__":
    asyncio.run(main())
