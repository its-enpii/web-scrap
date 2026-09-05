from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .key_storage_helper import append_key_to_file

class BaseFlow(ABC):
    name: str = "Base Flow"
    description: str = "Base Description"

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.output_mode = config.get("output_mode", "omni")  # "omni" atau "txt"
        self.output_file = config.get("output_file", "keys.txt")

    @abstractmethod
    async def run_flow(self, context: BrowserContext, main_page: Optional[Page], account: Dict[str, str], index: int, total: int) -> bool:
        """
        Menjalankan alur pendaftaran untuk satu akun.
        Mengembalikan True jika berhasil, False jika gagal.
        """
        pass

    async def setup(self, context: BrowserContext, main_page: Optional[Page]) -> bool:
        """
        Setup global awal sebelum iterasi akun (misal login portal admin/omni jika output_mode == 'omni').
        Default: return True.
        """
        return True

    def save_key(self, email: str, api_key: str, custom_filename: Optional[str] = None):
        """
        Helper untuk menyimpan key ke file .txt.
        """
        target_file = custom_filename or self.output_file
        append_key_to_file(target_file, email, api_key, self.name)
