from pathlib import Path

import pandas as pd
import pytest

from crypto_quant_lab.backtest import load_market_data, run_backtest
from crypto_quant_lab.config import load_config
from crypto_quant_lab.risk import RiskManager
from crypto_quant_lab.strategies import build_strategy


def test_load_market_data_rejects_missing_required_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "spread.csv"
    csv_path.write_text(
        "timestamp,close_primary\n"
        "2025-01-01T00:00:00Z,100.0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="缺少必要列: close_secondary"):
        load_market_data(
            csv_path,
            required_columns=["timestamp", "close_primary", "close_secondary"],
            expected_timeframe="1m",
        )


def test_load_market_data_rejects_misaligned_timestamps(tmp_path: Path) -> None:
    csv_path = tmp_path / "ohlcv.csv"
    csv_path.write_text(
        "timestamp,close\n"
        "2025-01-01T00:00:00Z,100.0\n"
        "2025-01-01T00:02:00Z,101.0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="时间序列未按 1m 对齐"):
        load_market_data(
            csv_path,
            required_columns=["timestamp", "close"],
            expected_timeframe="1m",
        )


def test_load_market_data_rejects_timestamps_not_on_timeframe_boundary(tmp_path: Path) -> None:
    csv_path = tmp_path / "ohlcv-offset.csv"
    csv_path.write_text(
        "timestamp,close\n"
        "2025-01-01T00:00:30Z,100.0\n"
        "2025-01-01T00:01:30Z,101.0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="时间序列未按 1m 对齐"):
        load_market_data(
            csv_path,
            required_columns=["timestamp", "close"],
            expected_timeframe="1m",
        )


def test_load_market_data_rejects_non_numeric_required_values(tmp_path: Path) -> None:
    csv_path = tmp_path / "ohlcv-invalid-close.csv"
    csv_path.write_text(
        "timestamp,close\n"
        "2025-01-01T00:00:00Z,100.0\n"
        "2025-01-01T00:01:00Z,not-a-number\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="close 列存在缺失或无法解析的数值"):
        load_market_data(
            csv_path,
            required_columns=["timestamp", "close"],
            expected_timeframe="1m",
        )


def test_run_backtest_rejects_duplicate_timestamps() -> None:
    config = load_config(Path("configs/example.toml"))
    strategy = build_strategy(config.get_strategy("btc_ma_cross"))
    market_data = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2025-01-01T00:00:00Z", "2025-01-01T00:00:00Z"],
                utc=True,
            ),
            "close": [100.0, 101.0],
        }
    )

    with pytest.raises(ValueError, match="timestamp 列必须严格递增且唯一"):
        run_backtest(
            strategy=strategy,
            market_data=market_data,
            risk_manager=RiskManager(config.risk),
            config=config.backtest,
        )


def test_run_backtest_rejects_strategy_timeframe_mismatch() -> None:
    config = load_config(Path("configs/example.toml"))
    strategy = build_strategy(config.get_strategy("btc_okx_binance_spread"))
    market_data = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2025-01-01T00:00:00Z", "2025-01-01T00:02:00Z"],
                utc=True,
            ),
            "close_primary": [100.0, 101.0],
            "close_secondary": [100.2, 101.3],
        }
    )

    with pytest.raises(ValueError, match="时间序列未按 1m 对齐"):
        run_backtest(
            strategy=strategy,
            market_data=market_data,
            risk_manager=RiskManager(config.risk),
            config=config.backtest,
        )
