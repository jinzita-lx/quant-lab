"""简单均线策略。"""

from __future__ import annotations

import pandas as pd

from crypto_quant_lab.domain import SignalAction, StrategySignal
from crypto_quant_lab.strategies.base import BaseStrategy


class SimpleMovingAverageStrategy(BaseStrategy):
    """以均线交叉为例的非套利策略。"""

    kind = "moving_average"

    def required_market_data_columns(self) -> list[str]:
        return ["timestamp", "close"]

    def warmup_period(self) -> int:
        return int(self.parameters().get("long_window", 20))

    def generate_signal(self, market_data: pd.DataFrame) -> StrategySignal:
        self.validate_market_data(market_data, ["close"])
        short_window = int(self.parameters().get("short_window", 5))
        long_window = int(self.parameters().get("long_window", 20))

        if len(market_data) < max(long_window, 2):
            return StrategySignal(
                strategy_name=self.name,
                symbol=self.symbol,
                action=SignalAction.HOLD,
                reason="样本不足，继续等待",
            )

        price_series = market_data["close"].astype(float)
        short_ma = price_series.rolling(short_window).mean()
        long_ma = price_series.rolling(long_window).mean()

        prev_short = short_ma.iloc[-2]
        prev_long = long_ma.iloc[-2]
        curr_short = short_ma.iloc[-1]
        curr_long = long_ma.iloc[-1]

        if pd.notna(prev_short) and pd.notna(prev_long) and curr_short > curr_long and prev_short <= prev_long:
            return StrategySignal(
                strategy_name=self.name,
                symbol=self.symbol,
                action=SignalAction.BUY,
                reason="短期均线上穿长期均线",
                metadata={"short_ma": float(curr_short), "long_ma": float(curr_long)},
            )
        if pd.notna(prev_short) and pd.notna(prev_long) and curr_short < curr_long and prev_short >= prev_long:
            return StrategySignal(
                strategy_name=self.name,
                symbol=self.symbol,
                action=SignalAction.SELL,
                reason="短期均线下穿长期均线",
                metadata={"short_ma": float(curr_short), "long_ma": float(curr_long)},
            )
        return StrategySignal(
            strategy_name=self.name,
            symbol=self.symbol,
            action=SignalAction.HOLD,
            reason="均线未发生有效交叉",
            metadata={"short_ma": float(curr_short), "long_ma": float(curr_long)},
        )
