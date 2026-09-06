from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from playwright.async_api import BrowserContext, Page
from .key_storage_helper import append_key_to_file
from .account_state import AccountState

class BaseFlow(ABC):
    name: str = "Base Flow"
    description: str = "Base Description"

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.output_mode = config.get("output_mode", "omni")  # "omni" atau "txt"
        self.output_file = config.get("output_file", "keys.txt")
        self.state: Optional[AccountState] = None
        self._current_account_email: Optional[str] = None

    def attach_state(self, provider: str) -> AccountState:
        self.state = AccountState(provider)
        return self.state

    def mark_stage(self, stage: str, error: str | None = None, retryable: bool = True):
        if self.state is None:
            return
        self._update_current_state(stage=stage, error=error, retryable=retryable, status="in-progress")

    def mark_success(self, key_hint: str | None = None):
        if self.state is None:
            return
        self._update_current_state(
            stage="done",
            status="success",
            error=None,
            retryable=True,
            key_hint=key_hint,
            key_created_at=datetime.now(timezone.utc).isoformat(),
        )

    def mark_failed(self, stage: str, error: str, retryable: bool):
        if self.state is None:
            return
        self._update_current_state(stage=stage, status="failed", error=error, retryable=retryable)

    def _update_current_state(self, **fields):
        if self.state is None or self._current_account_email is None:
            return
        self.state.update(self._current_account_email, **fields)

    def set_current_account(self, email: str | None):
        self._current_account_email = email

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
