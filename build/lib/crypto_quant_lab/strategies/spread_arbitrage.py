"""跨交易所价差套利占位策略。"""

from __future__ import annotations

import pandas as pd

from crypto_quant_lab.domain import SignalAction, StrategySignal
from crypto_quant_lab.strategies.base import BaseStrategy


class SpreadArbitrageStrategy(BaseStrategy):
    """用于表达套利信号，不直接处理复杂执行细节。"""

    kind = "spread_arbitrage"

    def required_market_data_columns(self) -> list[str]:
        primary_column = str(self.parameters().get("primary_price_column", "close_primary"))
        secondary_column = str(self.parameters().get("secondary_price_column", "close_secondary"))
        return ["timestamp", primary_column, secondary_column]

    def generate_signal(self, market_data: pd.DataFrame) -> StrategySignal:
        primary_column = str(self.parameters().get("primary_price_column", "close_primary"))
        secondary_column = str(self.parameters().get("secondary_price_column", "close_secondary"))
        self.validate_market_data(market_data, [primary_column, secondary_column])

        latest = market_data.iloc[-1]
        primary_price = float(latest[primary_column])
        secondary_price = float(latest[secondary_column])
        spread_bps = ((secondary_price - primary_price) / primary_price) * 10000
        entry_spread_bps = float(self.parameters().get("entry_spread_bps", 8.0))
        exit_spread_bps = float(self.parameters().get("exit_spread_bps", 3.0))

        if spread_bps >= entry_spread_bps:
            return StrategySignal(
                strategy_name=self.name,
                symbol=self.symbol,
                action=SignalAction.ENTER_SPREAD,
                reason="价差达到入场阈值",
                metadata={"spread_bps": spread_bps},
            )
        if spread_bps <= exit_spread_bps:
            return StrategySignal(
                strategy_name=self.name,
                symbol=self.symbol,
                action=SignalAction.EXIT_SPREAD,
                reason="价差回归，触发退出条件",
                metadata={"spread_bps": spread_bps},
            )
        return StrategySignal(
            strategy_name=self.name,
            symbol=self.symbol,
            action=SignalAction.HOLD,
            reason="价差未达阈值",
            metadata={"spread_bps": spread_bps},
        )
