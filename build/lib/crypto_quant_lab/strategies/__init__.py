"""策略导出与工厂。"""

from crypto_quant_lab.config import StrategyConfig
from crypto_quant_lab.strategies.base import BaseStrategy
from crypto_quant_lab.strategies.moving_average import SimpleMovingAverageStrategy
from crypto_quant_lab.strategies.spread_arbitrage import SpreadArbitrageStrategy

__all__ = [
    "BaseStrategy",
    "SimpleMovingAverageStrategy",
    "SpreadArbitrageStrategy",
    "build_strategy",
]


def build_strategy(config: StrategyConfig) -> BaseStrategy:
    """根据配置创建策略实例。"""

    mapping = {
        "moving_average": SimpleMovingAverageStrategy,
        "spread_arbitrage": SpreadArbitrageStrategy,
    }
    if config.kind not in mapping:
        raise ValueError(f"不支持的策略类型: {config.kind}")
    return mapping[config.kind](config)
