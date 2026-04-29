"""验证 ccxt 适配器把代理设置注入到 client 上。"""

from __future__ import annotations

from typing import Any

from crypto_quant_lab.config import ExchangeConfig
from crypto_quant_lab.exchanges.ccxt_adapter import CCXTExchangeAdapter


class FakeClient:
    """模拟 ccxt 4.x 客户端：暴露 https_proxy / http_proxy / proxies 等属性。"""

    def __init__(self) -> None:
        self.https_proxy: str | None = None
        self.http_proxy: str | None = None
        self.aiohttp_proxy: str | None = None
        self.proxies: dict[str, str] = {}


def _build_adapter_with_fake(
    config: ExchangeConfig, monkeypatch
) -> tuple[CCXTExchangeAdapter, FakeClient]:
    fake = FakeClient()

    class _FakeOkxClass:
        def __init__(self, _: dict[str, Any]) -> None:
            pass

        def __new__(cls, _: dict[str, Any]) -> Any:  # noqa: D401
            return fake

    import crypto_quant_lab.exchanges.ccxt_adapter as adapter_mod

    monkeypatch.setattr(adapter_mod.ccxt, "okx", _FakeOkxClass, raising=False)

    adapter = CCXTExchangeAdapter("okx", config)
    adapter._ensure_client()
    return adapter, fake


def test_https_proxy_from_config_is_pushed_into_client(monkeypatch) -> None:
    """ccxt 4.x 不允许同时设 http_proxy 和 https_proxy，统一只设 https_proxy。"""

    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)

    config = ExchangeConfig(https_proxy="http://127.0.0.1:7890")
    _, fake = _build_adapter_with_fake(config, monkeypatch)

    assert fake.https_proxy == "http://127.0.0.1:7890"
    assert fake.aiohttp_proxy == "http://127.0.0.1:7890"
    # 不应再设 http_proxy / proxies，避免触发 ccxt InvalidProxySettings
    assert fake.http_proxy is None
    assert fake.proxies == {}


def test_http_proxy_only_is_used_when_https_missing(monkeypatch) -> None:
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)

    config = ExchangeConfig(http_proxy="http://10.0.0.1:8080")
    _, fake = _build_adapter_with_fake(config, monkeypatch)

    # 即使只配了 http_proxy，也会被注入到 ccxt 的 https_proxy 字段
    assert fake.https_proxy == "http://10.0.0.1:8080"
    assert fake.http_proxy is None


def test_env_proxy_used_when_config_missing(monkeypatch) -> None:
    monkeypatch.setenv("https_proxy", "http://env-proxy:7890")
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)

    config = ExchangeConfig()
    _, fake = _build_adapter_with_fake(config, monkeypatch)

    assert fake.https_proxy == "http://env-proxy:7890"
    assert fake.http_proxy is None
