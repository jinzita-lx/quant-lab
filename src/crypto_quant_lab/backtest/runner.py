"""轻量回测骨架。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from crypto_quant_lab.config import BacktestConfig
from crypto_quant_lab.domain import SignalAction
from crypto_quant_lab.risk import RiskManager
from crypto_quant_lab.strategies.base import BaseStrategy


@dataclass(slots=True)
class BacktestResult:
    """回测结果摘要。"""

    strategy_name: str
    starting_capital: float
    ending_equity: float
    return_pct: float
    total_trades: int
    signals_seen: int
    gross_pnl: float = 0.0
    net_pnl: float = 0.0
    fees_paid: float = 0.0
    slippage_cost: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate_pct: float = 0.0
    equity_curve: list[dict[str, Any]] = field(default_factory=list)
    trade_log: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class SpreadPosition:
    """双腿价差持仓。"""

    quantity: float
    primary_entry_price: float
    secondary_entry_price: float
    primary_column: str
    secondary_column: str
    entry_cash_flow: float


def _calculate_mark_to_market_equity(
    *,
    cash: float,
    quantity: float,
    current_price: float,
    latest: pd.Series,
    spread_position: SpreadPosition | None,
) -> float:
    equity = cash + quantity * current_price
    if spread_position is not None:
        primary_price = float(latest[spread_position.primary_column])
        secondary_price = float(latest[spread_position.secondary_column])
        equity += (spread_position.quantity * primary_price) - (spread_position.quantity * secondary_price)
    return equity


def _calculate_drawdown_pct(equity: float, peak_equity: float) -> float:
    if peak_equity <= 0:
        return 0.0
    return max(0.0, ((peak_equity - equity) / peak_equity) * 100)


def load_market_data(
    csv_path: str | Path,
    required_columns: list[str] | None = None,
    numeric_columns: list[str] | None = None,
    expected_timeframe: str | None = None,
) -> pd.DataFrame:
    """从 CSV 读取行情数据并执行基础校验。"""

    frame = pd.read_csv(csv_path)
    if frame.empty:
        raise ValueError("CSV 数据为空")
    return _normalize_market_data(
        frame,
        required_columns=required_columns or ["timestamp"],
        numeric_columns=numeric_columns,
        expected_timeframe=expected_timeframe,
    )


def _normalize_market_data(
    frame: pd.DataFrame,
    required_columns: list[str],
    numeric_columns: list[str] | None,
    expected_timeframe: str | None,
) -> pd.DataFrame:
    normalized = frame.copy()
    required = list(dict.fromkeys(required_columns))
    missing = [column for column in required if column not in normalized.columns]
    if missing:
        raise ValueError(f"缺少必要列: {', '.join(missing)}")

    if "timestamp" in normalized.columns:
        normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True, errors="coerce")
        _validate_timestamp_index(normalized, expected_timeframe=expected_timeframe)

    if numeric_columns is None:
        numeric_targets = [column for column in required if column != "timestamp"]
    else:
        numeric_targets = list(dict.fromkeys(numeric_columns))
    for column in numeric_targets:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
        if normalized[column].isna().any():
            raise ValueError(f"{column} 列存在缺失或无法解析的数值")
    return normalized


def _validate_timestamp_index(frame: pd.DataFrame, expected_timeframe: str | None = None) -> None:
    """校验时间戳严格递增、唯一且满足期望粒度。"""

    timestamps = frame["timestamp"]
    if timestamps.isna().any():
        raise ValueError("timestamp 列存在无法解析的值")
    if timestamps.duplicated().any() or not timestamps.is_monotonic_increasing:
        raise ValueError("timestamp 列必须严格递增且唯一")

    if expected_timeframe:
        aligned = timestamps.dt.floor(_timeframe_to_frequency(expected_timeframe))
        if not aligned.eq(timestamps).all():
            raise ValueError(f"时间序列未按 {expected_timeframe} 对齐")
    if expected_timeframe and len(timestamps) >= 2:
        expected_delta = _timeframe_to_timedelta(expected_timeframe)
        deltas = timestamps.diff().dropna()
        if not deltas.eq(expected_delta).all():
            raise ValueError(f"时间序列未按 {expected_timeframe} 对齐")


def _timeframe_to_timedelta(timeframe: str) -> pd.Timedelta:
    value, unit = _split_timeframe(timeframe)
    if unit == "m":
        return pd.Timedelta(minutes=value)
    if unit == "h":
        return pd.Timedelta(hours=value)
    if unit == "d":
        return pd.Timedelta(days=value)
    raise ValueError(f"暂不支持的 timeframe: {timeframe}")


def _timeframe_to_frequency(timeframe: str) -> str:
    value, unit = _split_timeframe(timeframe)
    if unit == "m":
        return f"{value}min"
    if unit == "h":
        return f"{value}h"
    if unit == "d":
        return f"{value}d"
    raise ValueError(f"暂不支持的 timeframe: {timeframe}")


def _split_timeframe(timeframe: str) -> tuple[int, str]:
    normalized = timeframe.strip().lower()
    if len(normalized) < 2:
        raise ValueError(f"暂不支持的 timeframe: {timeframe}")
    unit = normalized[-1]
    if unit not in {"m", "h", "d"}:
        raise ValueError(f"暂不支持的 timeframe: {timeframe}")
    try:
        value = int(normalized[:-1])
    except ValueError as exc:
        raise ValueError(f"暂不支持的 timeframe: {timeframe}") from exc
    if value <= 0:
        raise ValueError(f"暂不支持的 timeframe: {timeframe}")
    return value, unit


def generate_sample_market_data(periods: int = 160, timeframe: str = "1h") -> pd.DataFrame:
    """生成可直接用于演示的样例 OHLCV 数据。"""

    timestamps = pd.date_range("2025-01-01", periods=periods, freq=_timeframe_to_frequency(timeframe), tz="UTC")
    baseline = pd.Series(range(periods), dtype=float)
    close = 100 + baseline * 0.4 + (baseline % 9) * 0.6
    open_ = close - 0.3
    high = close + 1.0
    low = close - 1.0
    volume = 1000 + baseline * 5
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def generate_sample_spread_data(periods: int = 160, timeframe: str = "1m") -> pd.DataFrame:
    """生成跨交易所价差演示数据。"""

    timestamps = pd.date_range("2025-01-01", periods=periods, freq=_timeframe_to_frequency(timeframe), tz="UTC")
    primary = pd.Series([30000 + i * 15 for i in range(periods)], dtype=float)
    secondary = primary + (pd.Series(range(periods), dtype=float) % 6) * 5 - 8
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "close_primary": primary,
            "close_secondary": secondary,
        }
    )


def run_backtest(
    strategy: BaseStrategy,
    market_data: pd.DataFrame,
    risk_manager: RiskManager,
    config: BacktestConfig,
    trading_start_index: int = 0,
) -> BacktestResult:
    """运行极简回测流程。"""

    if market_data.empty:
        raise ValueError("回测数据为空")
    if trading_start_index < 0:
        raise ValueError("trading_start_index 不能为负")

    market_data = _normalize_market_data(
        market_data,
        required_columns=strategy.required_market_data_columns(),
        numeric_columns=None,
        expected_timeframe=strategy.expected_timeframe(),
    )

    is_spread_strategy = strategy.kind == "spread_arbitrage"
    if "close" in market_data.columns:
        price_column = "close"
    else:
        price_column = str(strategy.parameters().get("primary_price_column", "close_primary"))
    primary_price_column = str(strategy.parameters().get("primary_price_column", price_column))
    secondary_price_column = str(strategy.parameters().get("secondary_price_column", "close_secondary"))

    cash = config.initial_capital
    quantity = 0.0
    entry_price: float | None = None
    entry_total_cost: float | None = None
    spread_position: SpreadPosition | None = None
    signals_seen = 0
    fees_paid = 0.0
    slippage_cost = 0.0
    peak_equity = config.initial_capital
    max_drawdown_pct = 0.0
    closed_trade_pnls: list[float] = []
    equity_curve: list[dict[str, Any]] = []
    trade_log: list[dict[str, Any]] = []

    for index in range(len(market_data)):
        if index < trading_start_index:
            continue
        window = market_data.iloc[: index + 1]
        latest = window.iloc[-1]
        signal = strategy.generate_signal(window)
        signals_seen += 1
        current_price = float(latest[price_column])

        if quantity > 0 and entry_price is not None:
            exit_reason = risk_manager.evaluate_exit(entry_price=entry_price, current_price=current_price)
            if exit_reason is not None:
                signal = signal.__class__(
                    strategy_name=signal.strategy_name,
                    symbol=signal.symbol,
                    action=SignalAction.SELL,
                    reason=exit_reason,
                    confidence=signal.confidence,
                    metadata={**signal.metadata, "forced_exit": True},
                )

        has_open_position = quantity > 0 or spread_position is not None
        if signal.action in {SignalAction.BUY, SignalAction.ENTER_SPREAD} and not has_open_position:
            decision = risk_manager.evaluate_entry(
                signal=signal,
                cash=cash,
                price=current_price,
                open_positions=1 if has_open_position else 0,
            )
            if decision.approved and decision.quantity > 0:
                if is_spread_strategy and signal.action is SignalAction.ENTER_SPREAD:
                    primary_price = float(latest[primary_price_column])
                    secondary_price = float(latest[secondary_price_column])
                    primary_execution_price = primary_price * (1 + config.slippage_bps / 10000)
                    secondary_execution_price = secondary_price * (1 - config.slippage_bps / 10000)
                    primary_notional = decision.quantity * primary_execution_price
                    secondary_notional = decision.quantity * secondary_execution_price
                    primary_fee = primary_notional * config.fee_rate
                    secondary_fee = secondary_notional * config.fee_rate
                    entry_slippage_cost = (decision.quantity * (primary_execution_price - primary_price)) + (
                        decision.quantity * (secondary_price - secondary_execution_price)
                    )
                    fees_paid += primary_fee + secondary_fee
                    slippage_cost += entry_slippage_cost
                    entry_cash_flow = (secondary_notional - secondary_fee) - (primary_notional + primary_fee)
                    cash += entry_cash_flow
                    spread_position = SpreadPosition(
                        quantity=decision.quantity,
                        primary_entry_price=primary_execution_price,
                        secondary_entry_price=secondary_execution_price,
                        primary_column=primary_price_column,
                        secondary_column=secondary_price_column,
                        entry_cash_flow=entry_cash_flow,
                    )
                    trade_log.append(
                        {
                            "timestamp": latest.get("timestamp"),
                            "action": signal.action.value,
                            "quantity": decision.quantity,
                            "primary_price": primary_execution_price,
                            "secondary_price": secondary_execution_price,
                            "fees": primary_fee + secondary_fee,
                            "slippage_cost": entry_slippage_cost,
                            "reason": signal.reason,
                            "spread_bps": signal.metadata.get("spread_bps"),
                        }
                    )
                else:
                    execution_price = current_price * (1 + config.slippage_bps / 10000)
                    notional = decision.quantity * execution_price
                    fee = notional * config.fee_rate
                    entry_slippage_cost = decision.quantity * (execution_price - current_price)
                    if cash >= notional + fee:
                        fees_paid += fee
                        slippage_cost += entry_slippage_cost
                        cash -= notional + fee
                        quantity = decision.quantity
                        entry_price = execution_price
                        entry_total_cost = notional + fee
                        trade_log.append(
                            {
                                "timestamp": latest.get("timestamp"),
                                "action": signal.action.value,
                                "price": execution_price,
                                "quantity": quantity,
                                "fees": fee,
                                "slippage_cost": entry_slippage_cost,
                                "reason": signal.reason,
                            }
                        )

        elif signal.action is SignalAction.EXIT_SPREAD and spread_position is not None:
            primary_price = float(latest[spread_position.primary_column])
            secondary_price = float(latest[spread_position.secondary_column])
            primary_execution_price = primary_price * (1 - config.slippage_bps / 10000)
            secondary_execution_price = secondary_price * (1 + config.slippage_bps / 10000)
            primary_notional = spread_position.quantity * primary_execution_price
            secondary_notional = spread_position.quantity * secondary_execution_price
            primary_fee = primary_notional * config.fee_rate
            secondary_fee = secondary_notional * config.fee_rate
            exit_slippage_cost = (spread_position.quantity * (primary_price - primary_execution_price)) + (
                spread_position.quantity * (secondary_execution_price - secondary_price)
            )
            fees_paid += primary_fee + secondary_fee
            slippage_cost += exit_slippage_cost
            exit_cash_flow = (primary_notional - primary_fee) - (secondary_notional + secondary_fee)
            trade_net_pnl = spread_position.entry_cash_flow + exit_cash_flow
            closed_trade_pnls.append(trade_net_pnl)
            cash += exit_cash_flow
            trade_log.append(
                {
                    "timestamp": latest.get("timestamp"),
                    "action": signal.action.value,
                    "quantity": spread_position.quantity,
                    "primary_price": primary_execution_price,
                    "secondary_price": secondary_execution_price,
                    "fees": primary_fee + secondary_fee,
                    "slippage_cost": exit_slippage_cost,
                    "realized_pnl": trade_net_pnl,
                    "reason": signal.reason,
                    "spread_bps": signal.metadata.get("spread_bps"),
                }
            )
            spread_position = None

        elif signal.action is SignalAction.SELL and quantity > 0:
            execution_price = current_price * (1 - config.slippage_bps / 10000)
            notional = quantity * execution_price
            fee = notional * config.fee_rate
            exit_slippage_cost = quantity * (current_price - execution_price)
            fees_paid += fee
            slippage_cost += exit_slippage_cost
            cash += notional - fee
            trade_net_pnl = (notional - fee) - (entry_total_cost or 0.0)
            closed_trade_pnls.append(trade_net_pnl)
            trade_log.append(
                {
                    "timestamp": latest.get("timestamp"),
                    "action": signal.action.value,
                    "price": execution_price,
                    "quantity": quantity,
                    "fees": fee,
                    "slippage_cost": exit_slippage_cost,
                    "realized_pnl": trade_net_pnl,
                    "reason": signal.reason,
                }
            )
            quantity = 0.0
            entry_price = None
            entry_total_cost = None

        current_equity = _calculate_mark_to_market_equity(
            cash=cash,
            quantity=quantity,
            current_price=current_price,
            latest=latest,
            spread_position=spread_position,
        )
        peak_equity = max(peak_equity, current_equity)
        current_drawdown_pct = _calculate_drawdown_pct(current_equity, peak_equity)
        max_drawdown_pct = max(max_drawdown_pct, current_drawdown_pct)
        equity_curve.append(
            {
                "timestamp": latest.get("timestamp"),
                "equity": current_equity,
                "drawdown_pct": current_drawdown_pct,
            }
        )

    final_price = float(market_data.iloc[-1][price_column])
    ending_equity = cash + quantity * final_price
    if spread_position is not None:
        final_primary_price = float(market_data.iloc[-1][spread_position.primary_column])
        final_secondary_price = float(market_data.iloc[-1][spread_position.secondary_column])
        ending_equity += (spread_position.quantity * final_primary_price) - (
            spread_position.quantity * final_secondary_price
        )
    net_pnl = ending_equity - config.initial_capital
    gross_pnl = net_pnl + fees_paid + slippage_cost
    return_pct = (net_pnl / config.initial_capital) * 100
    win_rate_pct = (
        (sum(1 for pnl in closed_trade_pnls if pnl > 0) / len(closed_trade_pnls)) * 100 if closed_trade_pnls else 0.0
    )

    return BacktestResult(
        strategy_name=strategy.name,
        starting_capital=config.initial_capital,
        ending_equity=ending_equity,
        return_pct=return_pct,
        total_trades=len(trade_log),
        signals_seen=signals_seen,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        fees_paid=fees_paid,
        slippage_cost=slippage_cost,
        max_drawdown_pct=max_drawdown_pct,
        win_rate_pct=win_rate_pct,
        equity_curve=equity_curve,
        trade_log=trade_log,
    )


@dataclass(slots=True)
class WalkForwardWindow:
    """单个 walk-forward 窗口的训练/测试范围与回测结果。"""

    train_start_index: int
    train_end_index: int
    test_start_index: int
    test_end_index: int
    result: BacktestResult


@dataclass(slots=True)
class WalkForwardResult:
    """walk-forward 聚合结果。"""

    total_windows: int
    window_results: list[WalkForwardWindow]
    average_return_pct: float
    total_net_pnl: float
    best_window_return_pct: float
    worst_window_return_pct: float


def run_walk_forward_backtest(
    strategy: BaseStrategy,
    market_data: pd.DataFrame,
    risk_manager: RiskManager,
    config: BacktestConfig,
    *,
    train_size: int,
    test_size: int,
    step_size: int | None = None,
) -> WalkForwardResult:
    """执行滑动窗口 walk-forward 回测。

    当前实现只将训练窗口作为指标预热区间，不对策略参数做再拟合；如需真正的参数再拟合，请在策略
    层覆写相应的训练钩子。
    """

    if train_size <= 0:
        raise ValueError("train_size 必须大于 0")
    if test_size <= 0:
        raise ValueError("test_size 必须大于 0")
    effective_step = step_size if step_size is not None else test_size
    if effective_step <= 0:
        raise ValueError("step_size 必须大于 0")

    total_required = train_size + test_size
    if len(market_data) < total_required:
        raise ValueError(
            f"数据量不足以执行 walk-forward: 至少需要 {total_required} 条, 实际 {len(market_data)}"
        )

    windows: list[WalkForwardWindow] = []
    start = 0
    while start + total_required <= len(market_data):
        train_end = start + train_size
        test_end = train_end + test_size
        window_data = market_data.iloc[start:test_end].reset_index(drop=True)
        window_result = run_backtest(
            strategy=strategy,
            market_data=window_data,
            risk_manager=risk_manager,
            config=config,
            trading_start_index=train_size,
        )
        windows.append(
            WalkForwardWindow(
                train_start_index=start,
                train_end_index=train_end,
                test_start_index=train_end,
                test_end_index=test_end,
                result=window_result,
            )
        )
        start += effective_step

    returns = [window.result.return_pct for window in windows]
    net_pnls = [window.result.net_pnl for window in windows]
    return WalkForwardResult(
        total_windows=len(windows),
        window_results=windows,
        average_return_pct=sum(returns) / len(windows),
        total_net_pnl=sum(net_pnls),
        best_window_return_pct=max(returns),
        worst_window_return_pct=min(returns),
    )
