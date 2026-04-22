"""风控骨架。"""

from __future__ import annotations

from dataclasses import dataclass

from crypto_quant_lab.config import RiskConfig
from crypto_quant_lab.domain import SignalAction, StrategySignal


@dataclass(slots=True)
class RiskDecision:
    """风控判断结果。"""

    approved: bool
    quantity: float
    reason: str


class RiskManager:
    """将仓位和退出规则集中管理。"""

    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def evaluate_entry(
        self,
        signal: StrategySignal,
        cash: float,
        price: float,
        open_positions: int,
    ) -> RiskDecision:
        if signal.action not in {SignalAction.BUY, SignalAction.ENTER_SPREAD}:
            return RiskDecision(approved=False, quantity=0.0, reason="当前信号不是入场动作")
        if open_positions >= self.config.max_open_positions:
            return RiskDecision(approved=False, quantity=0.0, reason="已达到最大持仓数")

        max_notional = min(cash, self.config.max_position_notional)
        if max_notional <= 0 or price <= 0:
            return RiskDecision(approved=False, quantity=0.0, reason="现金或价格无效")

        quantity = max_notional / price
        return RiskDecision(approved=True, quantity=quantity, reason="通过基础仓位限制")

    def evaluate_exit(self, entry_price: float, current_price: float) -> str | None:
        if entry_price <= 0 or current_price <= 0:
            return None
        pnl_ratio = (current_price - entry_price) / entry_price
        if pnl_ratio >= self.config.take_profit_pct:
            return "take_profit"
        if pnl_ratio <= -self.config.stop_loss_pct:
            return "stop_loss"
        return None
