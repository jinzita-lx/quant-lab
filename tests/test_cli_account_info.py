from typer.testing import CliRunner

from crypto_quant_lab.cli import app
from crypto_quant_lab.domain import TickerSnapshot


runner = CliRunner()


class DummyAccountAdapter:
    def __init__(self) -> None:
        self.closed = False
        self.ticker_calls: list[str] = []

    def fetch_accounts(self):
        return [
            {
                "id": "uid-1",
                "type": "2",
                "name": None,
                "info": {"label": "模拟盘", "uid": "uid-1"},
            }
        ]

    def fetch_balance(self):
        return {
            "total": {"USDT": 5000.0, "BTC": 1.0, "OKB": 100.0, "STALE": 0.0},
            "free": {"USDT": 5000.0, "BTC": 1.0, "OKB": 100.0, "STALE": 0.0},
            "used": {"USDT": 0.0, "BTC": 0.0, "OKB": 0.0, "STALE": 0.0},
            "info": {"data": [{"totalEq": "91483.47"}]},
        }

    def fetch_funding_balance(self):
        return [{"ccy": "USDT", "total": 10.0, "available": 10.0, "frozen": 0.0}]

    def fetch_positions(self):
        return []

    def fetch_ticker(self, symbol: str) -> TickerSnapshot:
        self.ticker_calls.append(symbol)
        prices = {"BTC/USDT": 85000.0, "OKB/USDT": 13.0}
        last = prices.get(symbol)
        if last is None:
            raise RuntimeError(f"no price for {symbol}")
        return TickerSnapshot(exchange="okx", symbol=symbol, last=last)

    def close(self):
        self.closed = True


def test_account_info_displays_accounts_balances_and_usd_valuation(monkeypatch) -> None:
    adapter = DummyAccountAdapter()

    def fake_create_exchange_adapter(exchange, config):
        return adapter

    monkeypatch.setattr(
        "crypto_quant_lab.cli.create_exchange_adapter", fake_create_exchange_adapter
    )

    result = runner.invoke(
        app,
        [
            "account-info",
            "--config",
            "configs/example.toml",
            "--exchange",
            "okx",
        ],
    )

    assert result.exit_code == 0, result.output
    output = result.stdout

    # 账户信息块（中文标题）
    assert "账户信息" in output
    assert "模拟盘" in output
    assert "uid-1" in output

    # 总权益
    assert "总权益" in output
    assert "91483.47" in output

    # 交易账户余额块
    assert "交易账户余额" in output
    assert "USDT" in output
    assert "BTC" in output
    assert "OKB" in output
    # 零余额资产应被过滤
    assert "STALE" not in output

    # 每个资产的美元估值列：BTC = 85000 * 1
    assert "85000" in output
    # USDT 的美元估值等于其数量
    assert "5000" in output

    # 资金账户块（中文标题）
    assert "资金账户余额" in output

    # 持仓块（中文标题）
    assert "持仓" in output

    assert adapter.closed is True


def test_account_info_handles_missing_ticker_gracefully(monkeypatch) -> None:
    class NoPriceAdapter(DummyAccountAdapter):
        def fetch_ticker(self, symbol: str) -> TickerSnapshot:
            raise RuntimeError("network down")

    adapter = NoPriceAdapter()
    monkeypatch.setattr(
        "crypto_quant_lab.cli.create_exchange_adapter", lambda e, c: adapter
    )

    result = runner.invoke(
        app,
        [
            "account-info",
            "--config",
            "configs/example.toml",
            "--exchange",
            "okx",
        ],
    )

    # 即使非 quote 资产的 ticker 拉取失败，也不应崩溃
    assert result.exit_code == 0, result.output
    assert "BTC" in result.stdout
    # USDT 的 USD 值仍然可以显示（等于数量）
    assert "5000" in result.stdout
    # 缺失价格时应落为占位符
    assert "N/A" in result.stdout or "不可用" in result.stdout
    assert adapter.closed is True
