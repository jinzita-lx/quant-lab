from pathlib import Path

from crypto_quant_lab.config import ExchangeConfig, NetworkConfig, ProjectConfig, load_config
from crypto_quant_lab.domain import MarketType


def test_load_example_config() -> None:
    config = load_config(Path("configs/example.toml"))
    assert config.app.default_exchange == "okx"
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


def test_exchange_config_http_proxy_falls_back_to_https(monkeypatch) -> None:
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    exchange = ExchangeConfig(https_proxy="http://127.0.0.1:7890")
    assert exchange.resolved_http_proxy() == "http://127.0.0.1:7890"


def test_exchange_config_explicit_http_proxy_wins(monkeypatch) -> None:
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9999")
    exchange = ExchangeConfig(http_proxy="http://127.0.0.1:7890")
    assert exchange.resolved_http_proxy() == "http://127.0.0.1:7890"


def test_okx_exchange_opts_into_paper_trading_in_example_config() -> None:
    config = load_config(Path("configs/example.toml"))
    assert config.get_exchange("okx").paper_trading is True
    assert config.get_exchange("binance").paper_trading is False


def _make_project(network: NetworkConfig | None = None, **exchange_kwargs) -> ProjectConfig:
    return ProjectConfig(
        app={"default_exchange": "okx"},
        exchanges={"okx": ExchangeConfig(**exchange_kwargs)},
        network=network or NetworkConfig(),
    )


def test_effective_proxy_prefers_exchange_over_network(monkeypatch) -> None:
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    project = _make_project(
        network=NetworkConfig(https_proxy="http://network:1"),
        https_proxy="http://exchange:2",
    )
    assert project.effective_proxy_for("okx") == {
        "https": "http://exchange:2",
        "http": "http://exchange:2",
    }


def test_effective_proxy_falls_back_to_network(monkeypatch) -> None:
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    project = _make_project(network=NetworkConfig(https_proxy="http://network:1"))
    assert project.effective_proxy_for("okx") == {
        "https": "http://network:1",
        "http": "http://network:1",
    }


def test_effective_proxy_falls_back_to_env(monkeypatch) -> None:
    monkeypatch.setenv("https_proxy", "http://envproxy:9")
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    project = _make_project()
    assert project.effective_proxy_for("okx") == {
        "https": "http://envproxy:9",
        "http": "http://envproxy:9",
    }
