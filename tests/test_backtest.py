from pathlib import Path

import pandas as pd
import pytest

from crypto_quant_lab.backtest import generate_sample_market_data, run_backtest
from crypto_quant_lab.config import load_config
from crypto_quant_lab.risk import RiskManager
from crypto_quant_lab.strategies import build_strategy


def test_moving_average_backtest_runs() -> None:
    config = load_config(Path("configs/example.toml"))
    strategy = build_strategy(config.get_strategy("btc_ma_cross"))
    result = run_backtest(
        strategy=strategy,
        market_data=generate_sample_market_data(),
        risk_manager=RiskManager(config.risk),
        config=config.backtest,
    )
    assert result.signals_seen > 0
    assert result.ending_equity > 0


def test_spread_backtest_realizes_profit_when_spread_converges() -> None:
    config = load_config(Path("configs/example.toml"))
    strategy = build_strategy(config.get_strategy("btc_okx_binance_spread"))
    market_data = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-01-01T00:00:00Z",
                    "2025-01-01T00:01:00Z",
                    "2025-01-01T00:02:00Z",
                ],
                utc=True,
            ),
            "close_primary": [100.0, 100.0, 100.0],
            "close_secondary": [100.2, 100.02, 100.01],
        }
    )

    result = run_backtest(
        strategy=strategy,
        market_data=market_data,
        risk_manager=RiskManager(
            config.risk.model_copy(
                update={
                    "max_position_notional": 1000.0,
                    "take_profit_pct": 1.0,
                    "stop_loss_pct": 1.0,
                }
            )
        ),
        config=config.backtest.model_copy(
            update={
                "initial_capital": 1000.0,
                "fee_rate": 0.0,
                "slippage_bps": 0.0,
            }
        ),
    )

    assert result.total_trades == 2
    assert result.ending_equity == pytest.approx(1001.8)
    assert result.return_pct > 0
    assert result.gross_pnl == pytest.approx(1.8)
    assert result.net_pnl == pytest.approx(1.8)
    assert result.trade_log[0]["primary_price"] == pytest.approx(100.0)
    assert result.trade_log[0]["secondary_price"] == pytest.approx(100.2)


def test_spread_backtest_tracks_fee_breakdown() -> None:
    config = load_config(Path("configs/example.toml"))
    strategy = build_strategy(config.get_strategy("btc_okx_binance_spread"))
    market_data = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-01-01T00:00:00Z",
                    "2025-01-01T00:01:00Z",
                    "2025-01-01T00:02:00Z",
                ],
                utc=True,
            ),
            "close_primary": [100.0, 100.0, 100.0],
            "close_secondary": [100.2, 100.02, 100.01],
        }
    )

    result = run_backtest(
        strategy=strategy,
        market_data=market_data,
        risk_manager=RiskManager(
            config.risk.model_copy(
                update={
                    "max_position_notional": 1000.0,
                    "take_profit_pct": 1.0,
                    "stop_loss_pct": 1.0,
                }
            )
        ),
        config=config.backtest.model_copy(
            update={
                "initial_capital": 1000.0,
                "fee_rate": 0.0005,
                "slippage_bps": 0.0,
            }
        ),
    )

    assert result.gross_pnl == pytest.approx(1.8)
    assert result.fees_paid == pytest.approx(2.0011)
    assert result.slippage_cost == pytest.approx(0.0)
    assert result.net_pnl == pytest.approx(-0.2011)


def test_backtest_reports_equity_curve_and_drawdown() -> None:
    config = load_config(Path("configs/example.toml"))
    strategy = build_strategy(
        config.get_strategy("btc_ma_cross").model_copy(
            update={
                "name": "btc_ma_fast",
                "params": {"short_window": 1, "long_window": 2},
            }
        )
    )
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
            "close": [100.0, 90.0, 100.0, 50.0],
        }
    )

    result = run_backtest(
        strategy=strategy,
        market_data=market_data,
        risk_manager=RiskManager(
            config.risk.model_copy(
                update={
                    "max_position_notional": 1000.0,
                    "take_profit_pct": 1.0,
                    "stop_loss_pct": 1.0,
                }
            )
        ),
        config=config.backtest.model_copy(
            update={
                "initial_capital": 1000.0,
                "fee_rate": 0.0,
                "slippage_bps": 0.0,
            }
        ),
    )

    assert len(result.equity_curve) == 4
    assert result.equity_curve[0]["equity"] == pytest.approx(1000.0)
    assert result.equity_curve[-1]["equity"] == pytest.approx(500.0)
    assert result.max_drawdown_pct == pytest.approx(50.0)
    assert result.win_rate_pct == pytest.approx(0.0)


def test_spread_backtest_reports_win_rate() -> None:
    config = load_config(Path("configs/example.toml"))
    strategy = build_strategy(config.get_strategy("btc_okx_binance_spread"))
    market_data = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2025-01-01T00:00:00Z",
                    "2025-01-01T00:01:00Z",
                    "2025-01-01T00:02:00Z",
                ],
                utc=True,
            ),
            "close_primary": [100.0, 100.0, 100.0],
            "close_secondary": [100.2, 100.02, 100.01],
        }
    )

    result = run_backtest(
        strategy=strategy,
        market_data=market_data,
        risk_manager=RiskManager(
            config.risk.model_copy(
                update={
                    "max_position_notional": 1000.0,
                    "take_profit_pct": 1.0,
                    "stop_loss_pct": 1.0,
                }
            )
        ),
        config=config.backtest.model_copy(
            update={
                "initial_capital": 1000.0,
                "fee_rate": 0.0,
                "slippage_bps": 0.0,
            }
        ),
    )

    assert len(result.equity_curve) == 3
    assert result.equity_curve[1]["equity"] == pytest.approx(1001.8)
    assert result.max_drawdown_pct == pytest.approx(0.0)
    assert result.win_rate_pct == pytest.approx(100.0)
