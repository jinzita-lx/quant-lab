"""交易所适配器工厂。"""

from __future__ import annotations

from crypto_quant_lab.config import ExchangeConfig
from crypto_quant_lab.exchanges.ccxt_adapter import CCXTExchangeAdapter

SUPPORTED_EXCHANGES = {"binance", "okx"}


def create_exchange_adapter(name: str, config: ExchangeConfig) -> CCXTExchangeAdapter:
    """创建交易所适配器实例。"""

    if name not in SUPPORTED_EXCHANGES:
        raise ValueError(f"当前仅支持: {', '.join(sorted(SUPPORTED_EXCHANGES))}")
    return CCXTExchangeAdapter(exchange_name=name, config=config)
