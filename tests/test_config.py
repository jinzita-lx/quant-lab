from pathlib import Path

from crypto_quant_lab.config import ExchangeConfig, load_config
from crypto_quant_lab.domain import MarketType


def test_load_example_config() -> None:
    config = load_config(Path("configs/example.toml"))
    assert config.app.default_exchange == "binance"
    assert len(config.strategies) == 2
    assert "okx" in config.exchanges
    assert config.get_strategy("btc_ma_cross").symbol == "BTC/USDT"
    assert config.get_strategy("btc_okx_binance_spread").instrument_id.market_type is MarketType.SPOT


def test_exchange_config_paper_trading_defaults_to_false() -> None:
    exchange = ExchangeConfig()
    assert exchange.paper_trading is False


def test_exchange_config_https_proxy_defaults_to_none() -> None:
    exchange = ExchangeConfig()
    assert exchange.https_proxy is None


def test_exchange_config_resolves_https_proxy_from_env(monkeypatch) -> None:
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:7890")
    exchange = ExchangeConfig()
    assert exchange.resolved_https_proxy() == "http://127.0.0.1:7890"


def test_exchange_config_explicit_https_proxy_wins_over_env(monkeypatch) -> None:
    monkeypatch.setenv("https_proxy", "http://127.0.0.1:9999")
    exchange = ExchangeConfig(https_proxy="http://127.0.0.1:7890")
    assert exchange.resolved_https_proxy() == "http://127.0.0.1:7890"


def test_okx_exchange_opts_into_paper_trading_in_example_config() -> None:
    config = load_config(Path("configs/example.toml"))
    assert config.get_exchange("okx").paper_trading is True
    assert config.get_exchange("binance").paper_trading is False
