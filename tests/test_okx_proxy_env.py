from pathlib import Path

from crypto_quant_lab.config import load_config
from crypto_quant_lab.exchanges.ccxt_adapter import CCXTExchangeAdapter


def test_okx_client_enables_env_proxy_trust() -> None:
    project = load_config(Path("configs/example.toml"))
    adapter = CCXTExchangeAdapter("okx", project.get_exchange("okx"))

    client = adapter._ensure_client()

    assert client.requests_trust_env is True
    assert client.aiohttp_trust_env is True
    assert client.session.trust_env is True
