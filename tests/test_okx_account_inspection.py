from pathlib import Path

import pytest

from crypto_quant_lab.config import ExchangeConfig, load_config
from crypto_quant_lab.exchanges.ccxt_adapter import CCXTExchangeAdapter


class FakeReadOnlyClient:
    def __init__(self) -> None:
        self.sandbox_enabled = False
        self.fetch_balance_calls: list[dict] = []
        self.fetch_positions_calls: list[dict] = []
        self.private_get_asset_balances_calls: list[dict] = []

    def set_sandbox_mode(self, enabled: bool) -> None:
        self.sandbox_enabled = enabled

    def fetch_accounts(self):
        return [
            {
                "id": "652163773448708373",
                "type": "2",
                "name": None,
                "info": {
                    "uid": "652163773448708373",
                    "label": "模拟盘",
                    "mainUid": "652163773448708373",
                },
            }
        ]

    def fetch_balance(self, params=None):
        self.fetch_balance_calls.append(params or {})
        return {
            "total": {"USDT": 5000.0, "BTC": 1.0, "ETH": 1.0, "OKB": 100.0, "STALE": 0.0},
            "free": {"USDT": 5000.0, "BTC": 1.0, "ETH": 1.0, "OKB": 100.0, "STALE": 0.0},
            "used": {"USDT": 0.0, "BTC": 0.0, "ETH": 0.0, "OKB": 0.0, "STALE": 0.0},
            "info": {"data": [{"totalEq": "91483.47"}]},
        }

    def fetch_positions(self, symbols=None, params=None):
        self.fetch_positions_calls.append({"symbols": symbols, "params": params or {}})
        return []

    def private_get_asset_balances(self, params=None):
        self.private_get_asset_balances_calls.append(params or {})
        return {
            "code": "0",
            "data": [
                {"ccy": "USDT", "bal": "10.0", "availBal": "10.0", "frozenBal": "0"},
                {"ccy": "BTC", "bal": "0", "availBal": "0", "frozenBal": "0"},
            ],
        }


@pytest.fixture
def okx_config() -> ExchangeConfig:
    project = load_config(Path("configs/example.toml"))
    return project.get_exchange("okx").model_copy(
        update={
            "api_key": "test-key",
            "api_secret": "test-secret",
            "password": "test-passphrase",
            "testnet": True,
        }
    )


@pytest.fixture
def binance_config() -> ExchangeConfig:
    project = load_config(Path("configs/example.toml"))
    return project.get_exchange("binance").model_copy(
        update={"api_key": "k", "api_secret": "s"}
    )


def test_fetch_accounts_returns_client_payload(okx_config: ExchangeConfig) -> None:
    adapter = CCXTExchangeAdapter("okx", okx_config)
    adapter._client = FakeReadOnlyClient()

    accounts = adapter.fetch_accounts()

    assert accounts[0]["info"]["label"] == "模拟盘"
    assert accounts[0]["id"] == "652163773448708373"


def test_fetch_balance_returns_totals_and_info(okx_config: ExchangeConfig) -> None:
    adapter = CCXTExchangeAdapter("okx", okx_config)
    fake = FakeReadOnlyClient()
    adapter._client = fake

    balance = adapter.fetch_balance()

    assert balance["total"]["USDT"] == 5000.0
    assert balance["total"]["BTC"] == 1.0
    assert balance["info"]["data"][0]["totalEq"] == "91483.47"
    assert fake.fetch_balance_calls == [{}]


def test_fetch_funding_balance_returns_normalized_non_zero_rows(okx_config: ExchangeConfig) -> None:
    adapter = CCXTExchangeAdapter("okx", okx_config)
    fake = FakeReadOnlyClient()
    adapter._client = fake

    funding = adapter.fetch_funding_balance()

    assert len(funding) == 1
    row = funding[0]
    assert row["ccy"] == "USDT"
    assert row["total"] == 10.0
    assert row["available"] == 10.0
    assert row["frozen"] == 0.0
    assert fake.private_get_asset_balances_calls == [{}]


def test_fetch_funding_balance_rejects_non_okx_exchange(binance_config: ExchangeConfig) -> None:
    adapter = CCXTExchangeAdapter("binance", binance_config)
    adapter._client = FakeReadOnlyClient()

    with pytest.raises(RuntimeError):
        adapter.fetch_funding_balance()


def test_fetch_positions_returns_client_result(okx_config: ExchangeConfig) -> None:
    adapter = CCXTExchangeAdapter("okx", okx_config)
    fake = FakeReadOnlyClient()
    adapter._client = fake

    positions = adapter.fetch_positions()

    assert positions == []
    assert fake.fetch_positions_calls == [{"symbols": None, "params": {}}]
