"""交易所适配层接口。"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from crypto_quant_lab.config import ExchangeConfig
from crypto_quant_lab.domain import ExchangeMetadata, TickerSnapshot


class ExchangeAdapter(ABC):
    """统一交易所访问接口。"""

    def __init__(self, exchange_name: str, config: ExchangeConfig) -> None:
        self.exchange_name = exchange_name
        self.config = config

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame:
        """获取标准 OHLCV 数据。"""

    @abstractmethod
    def fetch_ticker(self, symbol: str) -> TickerSnapshot:
        """获取最新行情。"""

    @abstractmethod
    def load_exchange_metadata(self) -> ExchangeMetadata:
        """加载并统一交易所标的元数据。"""

    @abstractmethod
    def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: float | None = None,
    ) -> dict:
        """创建订单。"""

    @abstractmethod
    def fetch_order(self, order_id: str, symbol: str | None = None, paper: bool = False) -> dict:
        """查询单笔订单。"""

    @abstractmethod
    def fetch_open_orders(self, symbol: str | None = None, paper: bool = False) -> list[dict]:
        """查询未完成订单。"""

    @abstractmethod
    def create_paper_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: float | None = None,
    ) -> dict:
        """在模拟盘中创建订单。"""

    @abstractmethod
    def close(self) -> None:
        """关闭底层客户端。"""
