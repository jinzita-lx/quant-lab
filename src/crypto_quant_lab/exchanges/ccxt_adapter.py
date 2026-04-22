"""基于 ccxt 的 Binance / OKX 适配器骨架。"""

from __future__ import annotations

from typing import Any

import pandas as pd

from crypto_quant_lab.config import ExchangeConfig
from crypto_quant_lab.domain import (
    ContractType,
    ExchangeMetadata,
    InstrumentId,
    InstrumentMetadata,
    MarketType,
    TickerSnapshot,
)
from crypto_quant_lab.exchanges.base import ExchangeAdapter

try:
    import ccxt  # type: ignore
except ImportError:  # pragma: no cover - 仅在依赖未安装时触发
    ccxt = None


class CCXTExchangeAdapter(ExchangeAdapter):
    """封装 ccxt 的基础公共能力。"""

    _OKX_PAPER_TRADING_FLAG = "1"

    def __init__(self, exchange_name: str, config: ExchangeConfig) -> None:
        super().__init__(exchange_name=exchange_name, config=config)
        self._client: Any | None = None
        self._metadata: ExchangeMetadata | None = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        if ccxt is None:
            raise RuntimeError("未安装 ccxt，请先执行 `pip install -e .`。")
        if not hasattr(ccxt, self.exchange_name):
            raise ValueError(f"ccxt 暂不支持交易所: {self.exchange_name}")

        credentials = self.config.resolved_credentials()
        client_kwargs: dict[str, Any] = {
            "enableRateLimit": True,
            "rateLimit": self.config.rate_limit_ms,
            # 让 ccxt 继承当前 shell 的 HTTP(S)_PROXY / NO_PROXY，
            # 否则 requests.Session 默认 trust_env=False，会绕过已配置的本地代理。
            "requests_trust_env": True,
            "aiohttp_trust_env": True,
        }
        if credentials["api_key"]:
            client_kwargs["apiKey"] = credentials["api_key"]
        if credentials["api_secret"]:
            client_kwargs["secret"] = credentials["api_secret"]
        if credentials["password"]:
            client_kwargs["password"] = credentials["password"]

        client_class = getattr(ccxt, self.exchange_name)
        client = client_class(client_kwargs)

        if self.config.testnet and hasattr(client, "set_sandbox_mode"):
            try:
                client.set_sandbox_mode(True)
            except Exception:
                pass

        self._client = client
        return client

    def load_exchange_metadata(self) -> ExchangeMetadata:
        if self._metadata is not None:
            return self._metadata
        client = self._ensure_client()
        raw_markets = client.load_markets()
        metadata = ExchangeMetadata(venue=self.exchange_name)

        for native_symbol, raw in raw_markets.items():
            instrument_id = self._parse_instrument_id(native_symbol=native_symbol, raw=raw)
            instrument = InstrumentMetadata(
                instrument_id=instrument_id,
                native_symbol=str(raw.get("symbol") or native_symbol),
                tick_size=self._to_float(raw.get("precision", {}).get("price")),
                lot_size=self._to_float(raw.get("limits", {}).get("amount", {}).get("min")),
                min_notional=self._to_float(raw.get("limits", {}).get("cost", {}).get("min")),
                aliases=self._collect_aliases(native_symbol=native_symbol, raw=raw, instrument_id=instrument_id),
                raw=raw,
            )
            metadata.add(instrument)
        self._metadata = metadata
        return metadata

    def _parse_instrument_id(self, native_symbol: str, raw: dict[str, Any]) -> InstrumentId:
        symbol = str(raw.get("symbol") or native_symbol)
        market_type = self._infer_market_type(raw)
        contract_type = ContractType.PERPETUAL if market_type is MarketType.PERPETUAL else ContractType.SPOT
        settle = str(raw.get("settle") or raw.get("quote") or "").upper() or None
        return InstrumentId.from_symbol(
            symbol,
            venue=self.exchange_name,
            market_type=market_type,
            contract_type=contract_type,
            settle=settle,
        )

    @staticmethod
    def _infer_market_type(raw: dict[str, Any]) -> MarketType:
        if raw.get("swap") or raw.get("contract") or raw.get("type") in {"swap", "future"}:
            return MarketType.PERPETUAL
        return MarketType.SPOT

    @staticmethod
    def _collect_aliases(
        native_symbol: str,
        raw: dict[str, Any],
        instrument_id: InstrumentId,
    ) -> tuple[str, ...]:
        aliases: list[str] = []
        for candidate in (native_symbol, raw.get("symbol"), raw.get("id")):
            if isinstance(candidate, str) and candidate.strip():
                aliases.append(candidate)
        base = raw.get("base")
        quote = raw.get("quote")
        settle = raw.get("settle")
        if isinstance(base, str) and isinstance(quote, str):
            aliases.append(f"{base}/{quote}")
            aliases.append(f"{base}-{quote}")
            aliases.append(f"{base}{quote}")
            if instrument_id.market_type is MarketType.PERPETUAL:
                settle_currency = str(settle or quote)
                aliases.append(f"{base}/{quote}:{settle_currency}")
                aliases.append(f"{base}-{quote}-SWAP")
        aliases.extend(instrument_id.aliases())
        seen: set[str] = set()
        ordered: list[str] = []
        for alias in aliases:
            normalized = alias.strip()
            if not normalized or normalized.upper() in seen:
                continue
            seen.add(normalized.upper())
            ordered.append(normalized)
        return tuple(ordered)

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        return float(value)

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame:
        client = self._ensure_client()
        rows = client.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=limit)
        frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        if not frame.empty:
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
        return frame

    def fetch_ticker(self, symbol: str) -> TickerSnapshot:
        client = self._ensure_client()
        raw = client.fetch_ticker(symbol)
        return TickerSnapshot(
            exchange=self.exchange_name,
            symbol=symbol,
            last=float(raw["last"]),
            bid=float(raw["bid"]) if raw.get("bid") is not None else None,
            ask=float(raw["ask"]) if raw.get("ask") is not None else None,
            raw=raw,
        )

    def create_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: float | None = None,
    ) -> dict:
        credentials = self.config.resolved_credentials()
        if not credentials["api_key"] or not credentials["api_secret"]:
            raise RuntimeError(f"{self.exchange_name} 尚未配置私有 API 凭证。")
        client = self._ensure_client()
        return client.create_order(symbol=symbol, type=order_type, side=side, amount=amount, price=price)

    def create_paper_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        order_type: str = "market",
        price: float | None = None,
    ) -> dict:
        credentials = self.config.resolved_credentials()
        if not credentials["api_key"] or not credentials["api_secret"]:
            raise RuntimeError(f"{self.exchange_name} 尚未配置私有 API 凭证。")
        client = self._ensure_client()
        return client.create_order(
            symbol=symbol,
            type=order_type,
            side=side,
            amount=amount,
            price=price,
            params=self._paper_trading_params(),
        )

    def fetch_order(self, order_id: str, symbol: str | None = None, paper: bool = False) -> dict:
        client = self._ensure_client()
        params = self._paper_trading_params() if paper else {}
        return client.fetch_order(order_id, symbol=symbol, params=params)

    def fetch_open_orders(self, symbol: str | None = None, paper: bool = False) -> list[dict]:
        client = self._ensure_client()
        params = self._paper_trading_params() if paper else {}
        return client.fetch_open_orders(symbol=symbol, params=params)

    def fetch_accounts(self) -> list[dict]:
        """获取账户元信息列表。"""

        client = self._ensure_client()
        return client.fetch_accounts()

    def fetch_balance(self) -> dict:
        """获取交易账户余额。"""

        client = self._ensure_client()
        return client.fetch_balance(params={})

    def fetch_positions(self) -> list[dict]:
        """获取持仓（衍生品）。"""

        client = self._ensure_client()
        return client.fetch_positions(symbols=None, params={})

    def fetch_funding_balance(self) -> list[dict]:
        """获取 OKX 资金账户余额，仅返回非零资产。"""

        if self.exchange_name != "okx":
            raise RuntimeError(f"{self.exchange_name} 暂不支持资金账户余额查询。")
        client = self._ensure_client()
        raw = client.private_get_asset_balances({})
        rows = (raw or {}).get("data") or []
        normalized: list[dict] = []
        for row in rows:
            total = self._safe_float(row.get("bal"))
            if total == 0.0:
                continue
            normalized.append(
                {
                    "ccy": row.get("ccy"),
                    "total": total,
                    "available": self._safe_float(row.get("availBal")),
                    "frozen": self._safe_float(row.get("frozenBal")),
                }
            )
        return normalized

    @staticmethod
    def _safe_float(value: Any) -> float:
        if value is None or value == "":
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _paper_trading_params(self) -> dict[str, str]:
        if self.exchange_name != "okx":
            raise RuntimeError(f"{self.exchange_name} 暂不支持模拟盘交易。")
        return {
            "tdMode": "cash",
            "x-simulated-trading": self._OKX_PAPER_TRADING_FLAG,
        }

    def close(self) -> None:
        if self._client is not None and hasattr(self._client, "close"):
            self._client.close()
