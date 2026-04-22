from crypto_quant_lab.domain import ContractType, InstrumentId, MarketType


def test_spot_symbols_normalize_to_same_identity() -> None:
    canonical = InstrumentId.from_symbol("BTC/USDT", venue="binance")
    dashed = InstrumentId.from_symbol("BTC-USDT", venue="binance")
    compact = InstrumentId.from_symbol("BTCUSDT", venue="binance")

    assert canonical == dashed == compact
    assert canonical.market_type is MarketType.SPOT
    assert canonical.base == "BTC"
    assert canonical.quote == "USDT"
    assert canonical.symbol == "BTC/USDT"
    assert canonical.key == "binance:spot:BTC/USDT"


def test_perpetual_identity_is_distinct_from_spot() -> None:
    spot = InstrumentId.from_symbol("BTC/USDT", venue="okx")
    perpetual = InstrumentId.from_symbol("BTC-USDT-SWAP", venue="okx")

    assert perpetual.market_type is MarketType.PERPETUAL
    assert perpetual.contract_type is ContractType.PERPETUAL
    assert perpetual.symbol == "BTC/USDT:USDT"
    assert perpetual.settle == "USDT"
    assert perpetual != spot
    assert perpetual.key == "okx:perpetual:BTC/USDT:USDT"


def test_market_metadata_hints_can_disambiguate_compact_perpetual_symbols() -> None:
    perpetual = InstrumentId.from_symbol(
        "BTCUSDT",
        venue="binance",
        market_type=MarketType.PERPETUAL,
        contract_type=ContractType.PERPETUAL,
        settle="USDT",
    )

    assert perpetual.market_type is MarketType.PERPETUAL
    assert perpetual.contract_type is ContractType.PERPETUAL
    assert perpetual.symbol == "BTC/USDT:USDT"
