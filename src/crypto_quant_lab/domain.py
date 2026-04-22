"""项目内共享的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_KNOWN_QUOTES = (
    "USDT",
    "USDC",
    "BUSD",
    "FDUSD",
    "TUSD",
    "DAI",
    "BTC",
    "ETH",
    "USD",
    "EUR",
)
_PERPETUAL_SUFFIXES = ("-SWAP", "-PERP", "_SWAP", "_PERP")


def _normalize_symbol_token(symbol: str) -> str:
    return symbol.strip().upper()


def _normalize_venue(venue: str) -> str:
    return venue.strip().lower()


def _split_pair(symbol: str) -> tuple[str, str]:
    normalized = _normalize_symbol_token(symbol)
    for delimiter in ("/", "-", "_"):
        if delimiter in normalized:
            base, quote = normalized.split(delimiter, maxsplit=1)
            if base and quote:
                return base, quote
            break

    for quote in _KNOWN_QUOTES:
        if normalized.endswith(quote) and len(normalized) > len(quote):
            return normalized[: -len(quote)], quote
    raise ValueError(f"无法解析交易对: {symbol}")


def _strip_perpetual_suffix(symbol: str) -> tuple[str, bool]:
    normalized = _normalize_symbol_token(symbol)
    for suffix in _PERPETUAL_SUFFIXES:
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)], True
    return normalized, False


class SignalAction(str, Enum):
    """标准化策略动作。"""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    ENTER_SPREAD = "enter_spread"
    EXIT_SPREAD = "exit_spread"


class MarketType(str, Enum):
    """统一市场类型。"""

    SPOT = "spot"
    PERPETUAL = "perpetual"


class ContractType(str, Enum):
    """统一合约类型。"""

    SPOT = "spot"
    PERPETUAL = "perpetual"


@dataclass(slots=True, frozen=True)
class InstrumentId:
    """统一交易标的身份。"""

    venue: str
    market_type: MarketType
    base: str
    quote: str
    settle: str | None = None
    contract_type: ContractType = ContractType.SPOT

    @property
    def symbol(self) -> str:
        if self.market_type is MarketType.PERPETUAL and self.settle:
            return f"{self.base}/{self.quote}:{self.settle}"
        return f"{self.base}/{self.quote}"

    @property
    def key(self) -> str:
        return f"{self.venue}:{self.market_type.value}:{self.symbol}"

    def aliases(self) -> tuple[str, ...]:
        if self.market_type is MarketType.PERPETUAL:
            settle = self.settle or self.quote
            return (
                self.symbol,
                f"{self.base}-{self.quote}-SWAP",
                f"{self.base}_{self.quote}_SWAP",
                f"{self.base}/{self.quote}:{settle}",
            )
        return (
            self.symbol,
            f"{self.base}-{self.quote}",
            f"{self.base}_{self.quote}",
            f"{self.base}{self.quote}",
        )

    @classmethod
    def from_symbol(
        cls,
        symbol: str,
        venue: str,
        *,
        market_type: MarketType | None = None,
        contract_type: ContractType | None = None,
        settle: str | None = None,
    ) -> InstrumentId:
        """从常见交易所符号写法解析统一标识。"""

        normalized = _normalize_symbol_token(symbol)
        venue_normalized = _normalize_venue(venue)
        normalized_settle = _normalize_symbol_token(settle) if settle else None
        inferred_market_type = market_type
        inferred_contract_type = contract_type
        stripped_symbol, has_perpetual_suffix = _strip_perpetual_suffix(normalized)

        if ":" in normalized:
            pair, settle = normalized.split(":", maxsplit=1)
            base, quote = _split_pair(pair)
            return cls(
                venue=venue_normalized,
                market_type=MarketType.PERPETUAL,
                base=base,
                quote=quote,
                settle=settle,
                contract_type=ContractType.PERPETUAL,
            )

        if has_perpetual_suffix or inferred_market_type is MarketType.PERPETUAL:
            base, quote = _split_pair(stripped_symbol)
            settle_currency = normalized_settle or quote
            return cls(
                venue=venue_normalized,
                market_type=MarketType.PERPETUAL,
                base=base,
                quote=quote,
                settle=settle_currency,
                contract_type=inferred_contract_type or ContractType.PERPETUAL,
            )

        base, quote = _split_pair(normalized)
        return cls(
            venue=venue_normalized,
            market_type=inferred_market_type or MarketType.SPOT,
            base=base,
            quote=quote,
            contract_type=inferred_contract_type or ContractType.SPOT,
        )


@dataclass(slots=True)
class InstrumentMetadata:
    """交易所返回的标的元数据。"""

    instrument_id: InstrumentId
    native_symbol: str
    tick_size: float | None = None
    lot_size: float | None = None
    min_notional: float | None = None
    aliases: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExchangeMetadata:
    """统一后的交易所市场元数据集合。"""

    venue: str
    instruments: dict[str, InstrumentMetadata] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    ambiguous_aliases: set[str] = field(default_factory=set)

    def add(self, metadata: InstrumentMetadata) -> None:
        canonical_key = metadata.instrument_id.key
        self.instruments[canonical_key] = metadata
        self._register_alias(metadata.instrument_id.symbol, canonical_key)
        self._register_alias(metadata.native_symbol, canonical_key)
        for alias in metadata.instrument_id.aliases():
            self._register_alias(alias, canonical_key)
        for alias in metadata.aliases:
            self._register_alias(alias, canonical_key)

    def resolve(self, symbol: str) -> InstrumentMetadata:
        try:
            instrument_id = InstrumentId.from_symbol(symbol, venue=self.venue)
        except ValueError:
            instrument_id = None
        if instrument_id is not None and instrument_id.key in self.instruments:
            return self.instruments[instrument_id.key]

        alias = _normalize_symbol_token(symbol)
        if alias in self.ambiguous_aliases:
            raise KeyError(f"标的别名存在歧义，请使用更明确的符号: {symbol}")
        canonical_key = self.aliases.get(alias)
        if canonical_key is None:
            raise KeyError(f"未找到标的元数据: {symbol}")
        return self.instruments[canonical_key]

    def _register_alias(self, symbol: str, canonical_key: str) -> None:
        alias = _normalize_symbol_token(symbol)
        if not alias or alias in self.ambiguous_aliases:
            return
        existing = self.aliases.get(alias)
        if existing is None or existing == canonical_key:
            self.aliases[alias] = canonical_key
            return
        self.aliases.pop(alias, None)
        self.ambiguous_aliases.add(alias)


@dataclass(slots=True)
class StrategySignal:
    """策略输出的统一信号对象。"""

    strategy_name: str
    symbol: str
    action: SignalAction
    reason: str
    confidence: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Position:
    """回测或执行层使用的简化持仓模型。"""

    symbol: str
    quantity: float = 0.0
    avg_price: float = 0.0
    strategy_name: str = ""


@dataclass(slots=True)
class TickerSnapshot:
    """交易所行情快照。"""

    exchange: str
    symbol: str
    last: float
    bid: float | None = None
    ask: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)
