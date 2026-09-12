from .base import BaseFlow
from .kiro_omni import KiroOmniFlow
from .opencode_zen import OpencodeZenFlow
from .openrouter import OpenRouterFlow
from .tokenrouter import TokenRouterFlow
from .bai import BAIFlow
from .qwencloud import QwenCloudFlow
from .unorouter import UnoRouterFlow
from .codecraft import CodeCraftFlow

AVAILABLE_FLOWS = {
    "kiro_omni": KiroOmniFlow,
    "opencode_zen": OpencodeZenFlow,
    "openrouter": OpenRouterFlow,
    "tokenrouter": TokenRouterFlow,
    "bai": BAIFlow,
    "qwencloud": QwenCloudFlow,
    "unorouter": UnoRouterFlow,
    "codecraft": CodeCraftFlow,
}
