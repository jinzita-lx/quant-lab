from pathlib import Path

import pandas as pd
import pytest

from crypto_quant_lab.backtest import run_backtest, run_walk_forward_backtest
from crypto_quant_lab.config import load_config
from crypto_quant_lab.risk import RiskManager
from crypto_quant_lab.strategies import build_strategy


def _fast_ma_strategy():
    config = load_config(Path("configs/example.toml"))
    strategy = build_strategy(
        config.get_strategy("btc_ma_cross").model_copy(
            update={
                "name": "btc_ma_fast",
                "params": {"short_window": 1, "long_window": 2},
            }
        )
    )
    risk_manager = RiskManager(
        config.risk.model_copy(
            update={
                "max_position_notional": 1000.0,
                "take_profit_pct": 1.0,
                "stop_loss_pct": 1.0,
            }
        )
    )
    backtest_config = config.backtest.model_copy(
        update={
            "initial_capital": 1000.0,
            "fee_rate": 0.0,
            "slippage_bps": 0.0,
        }
    )
    return strategy, risk_manager, backtest_config


def test_run_backtest_supports_trading_start_index_for_warmup() -> None:
    strategy, risk_manager, backtest_config = _fast_ma_strategy()
    market_data = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-01-01T00:00:00Z",
                    "2025-01-01T01:00:00Z",
                    "2025-01-01T02:00:00Z",
                    "2025-01-01T03:00:00Z",
                ],
                utc=True,
            ),
            "close": [100.0, 90.0, 100.0, 80.0],
        }
    )

    result = run_backtest(
        strategy=strategy,
        market_data=market_data,
        risk_manager=risk_manager,
        config=backtest_config,
        trading_start_index=2,
    )

    assert result.signals_seen == 2
    assert result.total_trades == 2
    assert len(result.equity_curve) == 2
    assert result.equity_curve[0]["equity"] == pytest.approx(1000.0)
    assert result.ending_equity == pytest.approx(800.0)
    assert result.return_pct == pytest.approx(-20.0)


def test_walk_forward_backtest_aggregates_multiple_windows() -> None:
    strategy, risk_manager, backtest_config = _fast_ma_strategy()
    market_data = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=12, freq="1h", tz="UTC"),
            "close": [100.0, 90.0, 100.0, 80.0] * 3,
        }
    )

    result = run_walk_forward_backtest(
        strategy=strategy,
        market_data=market_data,
        risk_manager=risk_manager,
        config=backtest_config,
        train_size=2,
        test_size=2,
        step_size=4,
    )

    assert result.total_windows == 3
    assert len(result.window_results) == 3
    assert result.average_return_pct == pytest.approx(-20.0)
    assert result.total_net_pnl == pytest.approx(-600.0)
    assert result.best_window_return_pct == pytest.approx(-20.0)
    assert result.worst_window_return_pct == pytest.approx(-20.0)
    assert [window.result.total_trades for window in result.window_results] == [2, 2, 2]


def test_walk_forward_backtest_requires_enough_data() -> None:
    strategy, risk_manager, backtest_config = _fast_ma_strategy()
    market_data = pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-01", periods=3, freq="1h", tz="UTC"),
            "close": [100.0, 90.0, 100.0],
        }
    )

    with pytest.raises(ValueError, match="数据量不足"):
        run_walk_forward_backtest(
            strategy=strategy,
            market_data=market_data,
            risk_manager=risk_manager,
            config=backtest_config,
            train_size=2,
            test_size=2,
        )
