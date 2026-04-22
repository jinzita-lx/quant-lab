from crypto_quant_lab.config import ExchangeConfig
from crypto_quant_lab.domain import MarketType
from crypto_quant_lab.exchanges.ccxt_adapter import CCXTExchangeAdapter


class FakeClient:
    def load_markets(self) -> dict[str, dict]:
        return {
            "BTC/USDT": {
                "symbol": "BTC/USDT",
                "base": "BTC",
                "quote": "USDT",
                "spot": True,
                "type": "spot",
                "precision": {"price": 0.1, "amount": 0.0001},
                "limits": {"amount": {"min": 0.0001}, "cost": {"min": 10.0}},
            },
            "BTC/USDT:USDT": {
                "symbol": "BTC/USDT:USDT",
                "base": "BTC",
                "quote": "USDT",
                "settle": "USDT",
                "swap": True,
                "contract": True,
                "type": "swap",
                "precision": {"price": 0.1, "amount": 0.001},
                "limits": {"amount": {"min": 0.001}, "cost": {"min": 5.0}},
            },
        }


def test_ccxt_adapter_loads_normalized_exchange_metadata(monkeypatch) -> None:
    adapter = CCXTExchangeAdapter("binance", ExchangeConfig())
    monkeypatch.setattr(adapter, "_ensure_client", lambda: FakeClient())

    metadata = adapter.load_exchange_metadata()
    spot = metadata.resolve("BTC-USDT")
    perpetual = metadata.resolve("BTC-USDT-SWAP")

    assert metadata.venue == "binance"
    assert spot.instrument_id.market_type is MarketType.SPOT
    assert spot.native_symbol == "BTC/USDT"
    assert perpetual.instrument_id.market_type is MarketType.PERPETUAL
    assert perpetual.native_symbol == "BTC/USDT:USDT"
    assert perpetual.tick_size == 0.1
    assert perpetual.lot_size == 0.001
    assert perpetual.min_notional == 5.0
    assert metadata.resolve("BTC/USDT:USDT").instrument_id.market_type is MarketType.PERPETUAL
