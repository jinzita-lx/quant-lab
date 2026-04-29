from pathlib import Path
import json

from typer.testing import CliRunner

from crypto_quant_lab import __version__
from crypto_quant_lab.cli import app


runner = CliRunner()


def test_version_command_prints_package_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.stdout == f"quant-lab {__version__}\n"


def test_walk_forward_command_prints_aggregate_metrics() -> None:
    result = runner.invoke(
        app,
        [
            "walk-forward",
            "--config",
            "configs/example.toml",
            "--strategy",
            "btc_ma_cross",
            "--train-size",
            "20",
            "--test-size",
            "10",
        ],
    )

    assert result.exit_code == 0
    assert "窗口数:" in result.stdout
    assert "平均收益率:" in result.stdout
    assert '"return_pct"' in result.stdout


def test_paper_orders_command_uses_adapter(monkeypatch) -> None:
    captured = {}

    class DummyAdapter:
        def fetch_open_orders(self, symbol=None, paper=False):
            captured["symbol"] = symbol
            captured["paper"] = paper
            return [{"id": "demo-order", "symbol": symbol, "status": "open"}]

        def close(self):
            captured["closed"] = True

    def fake_create_exchange_adapter(exchange, config):
        captured["exchange"] = exchange
        return DummyAdapter()

    monkeypatch.setattr("crypto_quant_lab.cli.create_exchange_adapter", fake_create_exchange_adapter)

    result = runner.invoke(
        app,
        [
            "paper-orders",
            "--config",
            "configs/example.toml",
            "--exchange",
            "okx",
            "--symbol",
            "BTC/USDT",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "exchange": "okx",
        "symbol": "BTC/USDT",
        "paper": True,
        "closed": True,
    }
    payload = json.loads(result.stdout)
    assert payload[0]["id"] == "demo-order"


def test_paper_order_command_uses_adapter(monkeypatch) -> None:
    captured = {}

    class DummyAdapter:
        def create_paper_order(self, symbol, side, amount, order_type="market", price=None):
            captured.update(
                {
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "order_type": order_type,
                    "price": price,
                }
            )
            return {"id": "demo-order", "symbol": symbol, "side": side, "amount": amount}

        def close(self):
            captured["closed"] = True

    def fake_create_exchange_adapter(exchange, config):
        captured["exchange"] = exchange
        return DummyAdapter()

    monkeypatch.setattr("crypto_quant_lab.cli.create_exchange_adapter", fake_create_exchange_adapter)

    result = runner.invoke(
        app,
        [
            "paper-order",
            "--config",
            "configs/example.toml",
            "--exchange",
            "okx",
            "--symbol",
            "BTC/USDT",
            "--side",
            "buy",
            "--amount",
            "0.01",
        ],
    )

    assert result.exit_code == 0
    assert captured == {
        "exchange": "okx",
        "symbol": "BTC/USDT",
        "side": "buy",
        "amount": 0.01,
        "order_type": "market",
        "price": None,
        "closed": True,
    }
    payload = json.loads(result.stdout)
    assert payload["id"] == "demo-order"


def test_paper_order_command_refuses_when_paper_trading_disabled(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("adapter should not be created when paper_trading is disabled")

    monkeypatch.setattr("crypto_quant_lab.cli.create_exchange_adapter", fail_if_called)

    result = runner.invoke(
        app,
        [
            "paper-order",
            "--config",
            "configs/example.toml",
            "--exchange",
            "binance",
            "--symbol",
            "BTC/USDT",
            "--side",
            "buy",
            "--amount",
            "0.01",
        ],
    )

    assert result.exit_code != 0
    assert "paper_trading" in result.output


def test_paper_orders_command_refuses_when_paper_trading_disabled(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("adapter should not be created when paper_trading is disabled")

    monkeypatch.setattr("crypto_quant_lab.cli.create_exchange_adapter", fail_if_called)

    result = runner.invoke(
        app,
        [
            "paper-orders",
            "--config",
            "configs/example.toml",
            "--exchange",
            "binance",
        ],
    )

    assert result.exit_code != 0
    assert "paper_trading" in result.output
