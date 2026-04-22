"""配置加载与校验。"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_quant_lab.domain import InstrumentId

_TIMEFRAME_PATTERN = re.compile(r"^[1-9][0-9]*[mhd]$")


def _normalize_non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} 不能为空")
    return normalized


def _normalize_exchange_name(value: str) -> str:
    return _normalize_non_empty(value, "exchange").lower()


def _normalize_timeframe(value: str) -> str:
    normalized = _normalize_non_empty(value, "timeframe").lower()
    if not _TIMEFRAME_PATTERN.fullmatch(normalized):
        raise ValueError(f"不支持的 timeframe: {value}")
    return normalized


class AppConfig(BaseModel):
    """应用基础配置。"""

    model_config = ConfigDict(extra="forbid")

    name: str = "crypto-quant-lab"
    env: str = "dev"
    default_exchange: str = "binance"
    quote_currency: str = "USDT"

    @field_validator("name", "env")
    @classmethod
    def _validate_text_fields(cls, value: str) -> str:
        return _normalize_non_empty(value, "app 配置")

    @field_validator("default_exchange")
    @classmethod
    def _validate_default_exchange(cls, value: str) -> str:
        return _normalize_exchange_name(value)

    @field_validator("quote_currency")
    @classmethod
    def _validate_quote_currency(cls, value: str) -> str:
        return _normalize_non_empty(value, "quote_currency").upper()


class BacktestConfig(BaseModel):
    """回测配置。"""

    model_config = ConfigDict(extra="forbid")

    initial_capital: float = 100000.0
    fee_rate: float = 0.0005
    slippage_bps: float = 2.0
    timeframe: str = "1h"

    @field_validator("timeframe")
    @classmethod
    def _validate_timeframe(cls, value: str) -> str:
        return _normalize_timeframe(value)


class RiskConfig(BaseModel):
    """风控参数。"""

    model_config = ConfigDict(extra="forbid")

    max_position_notional: float = 10000.0
    max_daily_loss_pct: float = 0.05
    take_profit_pct: float = 0.04
    stop_loss_pct: float = 0.02
    max_open_positions: int = 3


class ExchangeConfig(BaseModel):
    """交易所配置。"""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    api_key: str | None = None
    api_secret: str | None = None
    password: str | None = None
    api_key_env: str | None = None
    api_secret_env: str | None = None
    password_env: str | None = None
    testnet: bool = True
    paper_trading: bool = False
    https_proxy: str | None = None
    rate_limit_ms: int = 1000

    @field_validator("rate_limit_ms")
    @classmethod
    def _validate_rate_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("rate_limit_ms 必须大于 0")
        return value

    def resolved_credentials(self) -> dict[str, str | None]:
        """从配置或环境变量中解析凭证。"""

        return {
            "api_key": self.api_key or self._read_env(self.api_key_env),
            "api_secret": self.api_secret or self._read_env(self.api_secret_env),
            "password": self.password or self._read_env(self.password_env),
        }

    def resolved_https_proxy(self) -> str | None:
        """返回显式配置的 https_proxy，或退回到 shell 环境变量。"""

        if self.https_proxy:
            return self.https_proxy
        return os.getenv("https_proxy") or os.getenv("HTTPS_PROXY")

    @staticmethod
    def _read_env(name: str | None) -> str | None:
        if not name:
            return None
        return os.getenv(name)


class StrategyConfig(BaseModel):
    """策略配置。"""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str
    symbol: str
    exchange: str
    timeframe: str = "1h"
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name", "kind")
    @classmethod
    def _validate_identity_fields(cls, value: str) -> str:
        return _normalize_non_empty(value, "strategy 配置")

    @field_validator("exchange")
    @classmethod
    def _validate_exchange(cls, value: str) -> str:
        return _normalize_exchange_name(value)

    @field_validator("timeframe")
    @classmethod
    def _validate_timeframe(cls, value: str) -> str:
        return _normalize_timeframe(value)

    @model_validator(mode="after")
    def _normalize_symbol(self) -> StrategyConfig:
        instrument_id = InstrumentId.from_symbol(self.symbol, venue=self.exchange)
        self.symbol = instrument_id.symbol
        return self

    @property
    def instrument_id(self) -> InstrumentId:
        return InstrumentId.from_symbol(self.symbol, venue=self.exchange)


class ProjectConfig(BaseModel):
    """项目总配置。"""

    model_config = ConfigDict(extra="forbid")

    app: AppConfig = Field(default_factory=AppConfig)
    exchanges: dict[str, ExchangeConfig] = Field(default_factory=dict)
    strategies: list[StrategyConfig] = Field(default_factory=list)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    backtest: BacktestConfig = Field(default_factory=BacktestConfig)

    @field_validator("exchanges", mode="before")
    @classmethod
    def _normalize_exchange_mapping(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized: dict[str, Any] = {}
        for raw_name, config in value.items():
            name = _normalize_exchange_name(str(raw_name))
            if name in normalized:
                raise ValueError(f"重复的交易所配置: {name}")
            normalized[name] = config
        return normalized

    @model_validator(mode="after")
    def _validate_project_references(self) -> ProjectConfig:
        if self.app.default_exchange not in self.exchanges:
            raise ValueError(f"默认交易所未配置: {self.app.default_exchange}")
        for strategy in self.strategies:
            if strategy.exchange not in self.exchanges:
                raise ValueError(f"策略 {strategy.name} 引用了未配置交易所: {strategy.exchange}")
            if not self.exchanges[strategy.exchange].enabled:
                raise ValueError(f"策略 {strategy.name} 引用了未启用交易所: {strategy.exchange}")
        return self

    def get_exchange(self, name: str) -> ExchangeConfig:
        """获取指定交易所配置。"""

        normalized = _normalize_exchange_name(name)
        if normalized not in self.exchanges:
            raise KeyError(f"未找到交易所配置: {name}")
        return self.exchanges[normalized]

    def get_strategy(self, name: str) -> StrategyConfig:
        """按名称获取策略配置。"""

        normalized = _normalize_non_empty(name, "strategy name")
        for strategy in self.strategies:
            if strategy.name == normalized:
                return strategy
        raise KeyError(f"未找到策略配置: {name}")

    def redacted_dump(self) -> dict[str, Any]:
        """输出适合展示的脱敏配置。"""

        payload = self.model_dump()
        for exchange in payload.get("exchanges", {}).values():
            for field_name in ("api_key", "api_secret", "password"):
                if exchange.get(field_name):
                    exchange[field_name] = "***"
        return payload


def load_config(path: str | Path) -> ProjectConfig:
    """从 TOML 文件加载项目配置。"""

    config_path = Path(path)
    with config_path.open("rb") as handle:
        payload = tomllib.load(handle)
    return ProjectConfig.model_validate(payload)
