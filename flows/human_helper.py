import asyncio
import random
from playwright.async_api import Locator, Page

async def human_delay(min_sec: float = 0.5, max_sec: float = 1.2):
    """Memberikan jeda acak alami antara aksi."""
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)

async def _robust_click(locator: Locator, timeout_ms: int = 3000):
    """
    Klik dengan fallback force — mengatasi overlay transparan
    (iframe Turnstile / cookie banner) yang menutupi target.
    """
    try:
        await locator.click(timeout=timeout_ms)
    except Exception:
        try:
            await locator.click(timeout=timeout_ms, force=True)
        except Exception:
            pass

async def human_click(locator: Locator, pre_delay: float = 0.3, post_delay: float = 0.6):
    """
    Mengklik elemen dengan jeda hover/fokus alami sebelum dan sesudah klik.
    """
    try:
        await locator.wait_for(state="visible", timeout=15000)
    except Exception:
        pass
    try:
        await locator.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass
    await asyncio.sleep(random.uniform(pre_delay * 0.7, pre_delay * 1.3))
    await _robust_click(locator, timeout_ms=3000)
    await asyncio.sleep(random.uniform(post_delay * 0.7, post_delay * 1.3))

async def human_type(locator: Locator, text: str, min_delay: float = 0.03, max_delay: float = 0.08):
    """
    Mengetik karakter demi karakter dengan variasi jeda acak seperti manusia nyata.
    """
    try:
        await locator.wait_for(state="visible", timeout=15000)
    except Exception:
        pass
    await human_delay(0.1, 0.3)
    try:
        await locator.focus(timeout=2000)
    except Exception:
        await _robust_click(locator, timeout_ms=2000)
    await human_delay(0.1, 0.2)
    
    # Kosongkan input terlebih dahulu
    try:
        await locator.fill("")
    except Exception:
        pass
    await human_delay(0.1, 0.2)

    try:
        for char in text:
            await locator.type(char, delay=random.uniform(min_delay * 1000, max_delay * 1000))
            if char in ["@", ".", "-", "_"]:
                await asyncio.sleep(random.uniform(0.05, 0.15))
    except Exception:
        # Fallback jika type gagal
        await locator.fill(text)

    await human_delay(0.2, 0.5)
