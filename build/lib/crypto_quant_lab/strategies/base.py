"""策略基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from crypto_quant_lab.config import StrategyConfig
from crypto_quant_lab.domain import InstrumentId, StrategySignal


class BaseStrategy(ABC):
    """所有策略共享的最小接口。"""

    kind = "base"

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def symbol(self) -> str:
        return self.config.symbol

    @property
    def instrument_id(self) -> InstrumentId:
        return self.config.instrument_id

    def expected_timeframe(self) -> str:
        return self.config.timeframe

    def required_market_data_columns(self) -> list[str]:
        return ["timestamp"]

    def warmup_period(self) -> int:
        return 1

    def parameters(self) -> dict:
        return self.config.params

    def validate_market_data(self, market_data: pd.DataFrame, required_columns: list[str]) -> None:
        missing = [column for column in required_columns if column not in market_data.columns]
        if missing:
            raise ValueError(f"{self.name} 缺少必要列: {', '.join(missing)}")

    @abstractmethod
    def generate_signal(self, market_data: pd.DataFrame) -> StrategySignal:
        """根据市场数据生成标准化信号。"""
