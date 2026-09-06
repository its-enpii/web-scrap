import asyncio
import random
from playwright.async_api import Locator, Page

async def human_delay(min_sec: float = 0.5, max_sec: float = 1.2):
    """Memberikan jeda acak alami antara aksi."""
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)

async def human_type(locator: Locator, text: str, min_delay: float = 0.05, max_delay: float = 0.13):
    """
    Mengetik karakter demi karakter dengan variasi jeda acak seperti manusia nyata.
    """
    await locator.wait_for(state="visible", timeout=15000)
    await human_delay(0.2, 0.5)
    await _robust_click(locator)
    await human_delay(0.1, 0.3)
    
    # Kosongkan input terlebih dahulu jika ada isinya
    await locator.fill("")
    await human_delay(0.1, 0.2)

    for char in text:
        await locator.type(char, delay=random.uniform(min_delay * 1000, max_delay * 1000))
        # Sesekali beri jeda mikro antar kata
        if char in ["@", ".", "-", "_"]:
            await asyncio.sleep(random.uniform(0.1, 0.25))

    await human_delay(0.3, 0.7)

async def _robust_click(locator: Locator, timeout_ms: int = 8000):
    """
    Klik dengan fallback force — mengatasi overlay transparan
    (iframe Turnstile / cookie banner) yang menutupi target sehingga
    click Playwright menggantung di hit-target check sampai timeout.
    Force click tetap mengirim trusted event via CDP.
    """
    try:
        await locator.click(timeout=timeout_ms)
    except Exception:
        await locator.click(timeout=timeout_ms, force=True)

async def human_click(locator: Locator, pre_delay: float = 0.3, post_delay: float = 0.6):
    """
    Mengklik elemen dengan jeda hover/fokus alami sebelum dan sesudah klik.
    """
    await locator.wait_for(state="visible", timeout=15000)
    try:
        await locator.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass  # elemen sudah di viewport atau re-render; click punya auto-scroll sendiri
    await asyncio.sleep(random.uniform(pre_delay * 0.7, pre_delay * 1.3))
    await _robust_click(locator)
    await asyncio.sleep(random.uniform(post_delay * 0.7, post_delay * 1.3))
