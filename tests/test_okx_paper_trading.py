from pathlib import Path

import pytest

from crypto_quant_lab.config import ExchangeConfig, load_config
from crypto_quant_lab.exchanges.ccxt_adapter import CCXTExchangeAdapter


class FakeOKXClient:
    def __init__(self) -> None:
        self.sandbox_enabled = False
        self.orders = []
        self.fetch_order_calls = []
        self.fetch_open_orders_calls = []

    def set_sandbox_mode(self, enabled: bool) -> None:
        self.sandbox_enabled = enabled

    def create_order(self, symbol: str, type: str, side: str, amount: float, price: float | None = None, params=None):
        payload = {
            "id": "paper-order-1",
            "symbol": symbol,
            "type": type,
            "side": side,
            "amount": amount,
            "price": price,
            "params": params or {},
        }
        self.orders.append(payload)
        return payload

    def fetch_order(self, order_id: str, symbol: str | None = None, params=None):
        call = {"order_id": order_id, "symbol": symbol, "params": params or {}}
        self.fetch_order_calls.append(call)
        return {"id": order_id, "symbol": symbol, "status": "open", "params": params or {}}

    def fetch_open_orders(self, symbol: str | None = None, params=None):
        call = {"symbol": symbol, "params": params or {}}
        self.fetch_open_orders_calls.append(call)
        return [{"id": "paper-order-1", "symbol": symbol, "status": "open", "params": params or {}}]


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


def test_okx_paper_order_uses_sandbox_and_simulated_flag(okx_config: ExchangeConfig) -> None:
    adapter = CCXTExchangeAdapter("okx", okx_config)
    fake_client = FakeOKXClient()
    adapter._client = fake_client

    order = adapter.create_paper_order(symbol="BTC/USDT", side="buy", amount=0.01)

    assert order["id"] == "paper-order-1"
    assert fake_client.orders[0]["params"]["tdMode"] == "cash"
    assert fake_client.orders[0]["params"]["x-simulated-trading"] == "1"


def test_okx_paper_fetch_order_passes_simulated_flag(okx_config: ExchangeConfig) -> None:
    adapter = CCXTExchangeAdapter("okx", okx_config)
    fake_client = FakeOKXClient()
    adapter._client = fake_client

    order = adapter.fetch_order(order_id="paper-order-1", symbol="BTC/USDT", paper=True)

    assert order["status"] == "open"
    assert fake_client.fetch_order_calls[0]["params"]["x-simulated-trading"] == "1"


def test_okx_paper_fetch_open_orders_passes_simulated_flag(okx_config: ExchangeConfig) -> None:
    adapter = CCXTExchangeAdapter("okx", okx_config)
    fake_client = FakeOKXClient()
    adapter._client = fake_client

    orders = adapter.fetch_open_orders(symbol="BTC/USDT", paper=True)

    assert orders[0]["id"] == "paper-order-1"
    assert fake_client.fetch_open_orders_calls[0]["params"]["x-simulated-trading"] == "1"
