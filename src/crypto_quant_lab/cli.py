"""命令行入口。"""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path

import typer

from crypto_quant_lab import __version__
from crypto_quant_lab.backtest import (
    generate_sample_market_data,
    generate_sample_spread_data,
    load_market_data,
    run_backtest,
    run_walk_forward_backtest,
)
from crypto_quant_lab.config import ProjectConfig, load_config
from crypto_quant_lab.exchanges import create_exchange_adapter
from crypto_quant_lab.risk import RiskManager
from crypto_quant_lab.strategies import build_strategy

app = typer.Typer(help="Crypto Quant Lab 命令行工具")

_DEFAULT_CONFIG_FALLBACK = Path("configs/default.toml")
_ENV_FILE_NAMES = (".okx_demo_env", ".env")


def _parse_env_file(path: Path) -> dict[str, str]:
    """解析简单的 KEY=VALUE env 文件。支持 # 注释、空行、可选引号。"""

    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if (len(value) >= 2) and ((value[0] == value[-1]) and value[0] in {'"', "'"}):
            value = value[1:-1]
        result[key] = value
    return result


def _load_env_file_into_environ(path: Path, *, override: bool = False) -> int:
    """把 env 文件加载到 os.environ，默认不覆盖已存在的变量。返回新加载的键数。"""

    if not path.is_file():
        return 0
    try:
        pairs = _parse_env_file(path)
    except OSError:
        return 0
    loaded = 0
    for key, value in pairs.items():
        if not override and key in os.environ:
            continue
        os.environ[key] = value
        loaded += 1
    return loaded


def _autoload_env_files() -> None:
    """启动时按优先级搜索 env 文件并加载到 os.environ（不覆盖已有变量）。"""

    seen: set[Path] = set()
    candidates: list[Path] = []
    cwd = Path.cwd().resolve()
    for name in _ENV_FILE_NAMES:
        candidates.append(cwd / name)
    for parent in cwd.parents:
        for name in _ENV_FILE_NAMES:
            candidates.append(parent / name)
        if (parent / "pyproject.toml").is_file() or (parent / ".git").exists():
            break
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        _load_env_file_into_environ(resolved)


def _config_option() -> typer.models.OptionInfo:
    """统一的 --config 选项：未传时走 $QUANT_LAB_CONFIG，再回退到 configs/example.toml。"""

    return typer.Option(
        None,
        "--config",
        envvar="QUANT_LAB_CONFIG",
        exists=False,
        dir_okay=False,
        readable=True,
        help="配置文件路径。未传时使用 $QUANT_LAB_CONFIG 或 ./configs/default.toml。",
    )


def _exchange_option(help_text: str = "交易所名称，例如 okx") -> typer.models.OptionInfo:
    """统一的 --exchange 选项：未传时走 $QUANT_LAB_EXCHANGE，再回退到配置中的第一个交易所。"""

    return typer.Option(
        None,
        "--exchange",
        envvar="QUANT_LAB_EXCHANGE",
        help=f"{help_text}。未传时使用 $QUANT_LAB_EXCHANGE 或配置中的第一个交易所。",
    )


def _resolve_config_path(config: Path | None) -> Path:
    if config is not None:
        path = config
    else:
        path = _DEFAULT_CONFIG_FALLBACK
    if not path.exists():
        raise typer.BadParameter(
            f"找不到配置文件: {path}。请通过 --config 指定，或设置 $QUANT_LAB_CONFIG。",
            param_hint="--config",
        )
    if path.is_dir():
        raise typer.BadParameter(f"--config 应是文件而非目录: {path}", param_hint="--config")
    return path


def _load_project_config(config: Path | None) -> ProjectConfig:
    return load_config(_resolve_config_path(config))


def _resolve_exchange_name(project_config: ProjectConfig, exchange: str | None) -> str:
    """优先级：显式参数 > $QUANT_LAB_EXCHANGE（envvar 已由 Typer 注入到 exchange）> 配置默认 > 唯一交易所。"""

    if exchange:
        return exchange
    if project_config.app.default_exchange:
        return project_config.app.default_exchange
    if len(project_config.exchanges) == 1:
        return next(iter(project_config.exchanges))
    raise typer.BadParameter(
        "未指定交易所，且配置中没有 default_exchange。请通过 --exchange 指定或设置 $QUANT_LAB_EXCHANGE。",
        param_hint="--exchange",
    )


def _resolve_strategy(config: ProjectConfig, strategy_name: str | None):
    strategy_config = config.strategies[0] if strategy_name is None else config.get_strategy(strategy_name)
    return build_strategy(strategy_config)


def _exchange_config_with_proxy(project_config: ProjectConfig, exchange_name: str):
    """返回一份已经合并 [network] 兜底代理的 ExchangeConfig 副本。"""

    base = project_config.get_exchange(exchange_name)
    proxy = project_config.effective_proxy_for(exchange_name)
    if proxy["https"] == base.https_proxy and proxy["http"] == base.http_proxy:
        return base
    return base.model_copy(update={"https_proxy": proxy["https"], "http_proxy": proxy["http"]})


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"quant-lab {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        callback=_version_callback,
        is_eager=True,
        help="显示版本并退出。",
    ),
) -> None:
    """Crypto Quant Lab 命令行工具。"""

    _autoload_env_files()


@app.command("version")
def version() -> None:
    """显示当前版本。"""

    typer.echo(f"quant-lab {__version__}")


@app.command("show-config")
def show_config(config: Path | None = _config_option()) -> None:
    """显示配置内容并脱敏。"""

    payload = _load_project_config(config).redacted_dump()
    typer.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@app.command("list-strategies")
def list_strategies(config: Path | None = _config_option()) -> None:
    """列出已配置策略。"""

    project_config = _load_project_config(config)
    for strategy in project_config.strategies:
        typer.echo(f"{strategy.name} [{strategy.kind}] {strategy.exchange} {strategy.symbol} {strategy.timeframe}")


@app.command("backtest")
def backtest(
    config: Path | None = _config_option(),
    strategy: str | None = typer.Option(None, help="未指定时默认使用配置中的第一条策略"),
    csv: Path | None = typer.Option(None, exists=True, dir_okay=False, readable=True),
) -> None:
    """运行简化回测。"""

    project_config = _load_project_config(config)
    strategy_instance = _resolve_strategy(project_config, strategy)

    if csv is not None:
        market_data = load_market_data(
            csv,
            required_columns=strategy_instance.required_market_data_columns(),
            expected_timeframe=strategy_instance.expected_timeframe(),
        )
    elif strategy_instance.kind == "spread_arbitrage":
        market_data = generate_sample_spread_data(timeframe=strategy_instance.expected_timeframe())
    else:
        market_data = generate_sample_market_data(timeframe=strategy_instance.expected_timeframe())

    result = run_backtest(
        strategy=strategy_instance,
        market_data=market_data,
        risk_manager=RiskManager(project_config.risk),
        config=project_config.backtest,
    )

    typer.echo(f"策略: {result.strategy_name}")
    typer.echo(f"初始资金: {result.starting_capital:.2f}")
    typer.echo(f"期末权益: {result.ending_equity:.2f}")
    typer.echo(f"收益率: {result.return_pct:.2f}%")
    typer.echo(f"毛收益: {result.gross_pnl:.2f}")
    typer.echo(f"净收益: {result.net_pnl:.2f}")
    typer.echo(f"手续费: {result.fees_paid:.4f}")
    typer.echo(f"滑点成本: {result.slippage_cost:.4f}")
    typer.echo(f"最大回撤: {result.max_drawdown_pct:.2f}%")
    typer.echo(f"胜率: {result.win_rate_pct:.2f}%")
    typer.echo(f"信号数: {result.signals_seen}")
    typer.echo(f"交易事件数: {result.total_trades}")
    typer.echo(f"权益曲线点数: {len(result.equity_curve)}")
    if result.trade_log:
        typer.echo("最近交易事件:")
        for item in result.trade_log[-5:]:
            typer.echo(json.dumps(item, ensure_ascii=False, default=str))


@app.command("quote")
def quote(
    config: Path | None = _config_option(),
    exchange: str | None = _exchange_option("binance 或 okx"),
    symbol: str = typer.Option("BTC/USDT", help="交易对"),
) -> None:
    """获取公开行情快照。"""

    project_config = _load_project_config(config)
    exchange = _resolve_exchange_name(project_config, exchange)
    adapter = create_exchange_adapter(exchange, _exchange_config_with_proxy(project_config, exchange))
    try:
        ticker = adapter.fetch_ticker(symbol)
        typer.echo(json.dumps(asdict(ticker), ensure_ascii=False, indent=2))
    finally:
        adapter.close()


@app.command("walk-forward")
def walk_forward(
    config: Path | None = _config_option(),
    strategy: str | None = typer.Option(None, help="未指定时默认使用配置中的第一条策略"),
    csv: Path | None = typer.Option(None, exists=True, dir_okay=False, readable=True),
    train_size: int = typer.Option(..., min=1, help="训练窗口长度"),
    test_size: int = typer.Option(..., min=1, help="测试窗口长度"),
    step_size: int | None = typer.Option(None, min=1, help="窗口步长，默认等于测试窗口长度"),
) -> None:
    """运行 walk-forward 回测。"""

    project_config = _load_project_config(config)
    strategy_instance = _resolve_strategy(project_config, strategy)

    if csv is not None:
        market_data = load_market_data(
            csv,
            required_columns=strategy_instance.required_market_data_columns(),
            expected_timeframe=strategy_instance.expected_timeframe(),
        )
    elif strategy_instance.kind == "spread_arbitrage":
        market_data = generate_sample_spread_data(timeframe=strategy_instance.expected_timeframe())
    else:
        market_data = generate_sample_market_data(timeframe=strategy_instance.expected_timeframe())

    result = run_walk_forward_backtest(
        strategy=strategy_instance,
        market_data=market_data,
        risk_manager=RiskManager(project_config.risk),
        config=project_config.backtest,
        train_size=train_size,
        test_size=test_size,
        step_size=step_size,
    )

    typer.echo(f"策略: {strategy_instance.name}")
    typer.echo(f"窗口数: {result.total_windows}")
    typer.echo(f"平均收益率: {result.average_return_pct:.2f}%")
    typer.echo(f"最佳窗口收益率: {result.best_window_return_pct:.2f}%")
    typer.echo(f"最差窗口收益率: {result.worst_window_return_pct:.2f}%")
    typer.echo(f"累计净收益: {result.total_net_pnl:.2f}")
    for window in result.window_results:
        typer.echo(
            json.dumps(
                {
                    "train_range": [window.train_start_index, window.train_end_index],
                    "test_range": [window.test_start_index, window.test_end_index],
                    "return_pct": window.result.return_pct,
                    "net_pnl": window.result.net_pnl,
                    "total_trades": window.result.total_trades,
                },
                ensure_ascii=False,
            )
        )


def _require_paper_trading_enabled(project_config: ProjectConfig, exchange: str) -> None:
    exchange_config = project_config.get_exchange(exchange)
    if not exchange_config.paper_trading:
        raise typer.BadParameter(
            f"交易所 {exchange} 未开启 paper_trading，拒绝执行模拟盘指令。",
            param_hint="--exchange",
        )


def _require_private_credentials(project_config: ProjectConfig, exchange: str) -> None:
    """私有 API 命令前置检查：缺凭证时给中文提示并直接退出。"""

    exchange_config = project_config.get_exchange(exchange)
    creds = exchange_config.resolved_credentials()
    missing: list[str] = []
    if not creds.get("api_key"):
        missing.append(exchange_config.api_key_env or "api_key")
    if not creds.get("api_secret"):
        missing.append(exchange_config.api_secret_env or "api_secret")
    if exchange_config.password_env and not creds.get("password"):
        missing.append(exchange_config.password_env)
    if missing:
        hint = "、".join(missing)
        raise typer.BadParameter(
            f"交易所 {exchange} 缺少凭证：{hint}。请在 shell 中 export 对应环境变量后重试。",
            param_hint="--exchange",
        )


@app.command("paper-order")
def paper_order(
    config: Path | None = _config_option(),
    exchange: str | None = _exchange_option("当前支持 okx"),
    symbol: str = typer.Option(..., help="交易对，例如 BTC/USDT"),
    side: str = typer.Option(..., help="buy 或 sell"),
    amount: float = typer.Option(..., min=0.0, help="下单数量"),
    order_type: str = typer.Option("market", help="订单类型，例如 market 或 limit"),
    price: float | None = typer.Option(None, help="限价单价格"),
) -> None:
    """在模拟盘中创建订单。"""

    project_config = _load_project_config(config)
    exchange = _resolve_exchange_name(project_config, exchange)
    _require_paper_trading_enabled(project_config, exchange)
    _require_private_credentials(project_config, exchange)
    adapter = create_exchange_adapter(exchange, _exchange_config_with_proxy(project_config, exchange))
    try:
        order = adapter.create_paper_order(
            symbol=symbol,
            side=side,
            amount=amount,
            order_type=order_type,
            price=price,
        )
        typer.echo(json.dumps(order, ensure_ascii=False, indent=2))
    finally:
        adapter.close()


def _quote_usd_value(adapter, asset: str, amount: float, quote: str) -> float | None:
    if amount == 0:
        return 0.0
    if asset == quote:
        return amount
    try:
        ticker = adapter.fetch_ticker(f"{asset}/{quote}")
    except Exception:
        return None
    return amount * ticker.last


def _format_usd(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}"


@app.command("account-info")
def account_info(
    config: Path | None = _config_option(),
    exchange: str | None = _exchange_option("交易所名称，例如 okx"),
    quote: str = typer.Option("USDT", help="估值计价币种"),
) -> None:
    """只读查询账户信息、余额、资金账户与持仓。"""

    project_config = _load_project_config(config)
    exchange = _resolve_exchange_name(project_config, exchange)
    _require_private_credentials(project_config, exchange)
    adapter = create_exchange_adapter(exchange, _exchange_config_with_proxy(project_config, exchange))
    try:
        typer.echo("账户信息:")
        try:
            accounts = adapter.fetch_accounts()
        except Exception as exc:
            typer.echo(f"  (不可用: {exc})")
            accounts = []
        if not accounts:
            typer.echo("  (无)")
        for acc in accounts:
            info = acc.get("info") or {}
            typer.echo(
                f"  - id={acc.get('id')} type={acc.get('type')} "
                f"label={info.get('label')} uid={info.get('uid')}"
            )

        typer.echo("")
        try:
            balance = adapter.fetch_balance()
        except Exception as exc:
            typer.echo(f"余额查询失败: {exc}")
            balance = {}
        total_eq = None
        info_data = (balance.get("info") or {}).get("data") or []
        if info_data:
            total_eq = info_data[0].get("totalEq")
        typer.echo(f"总权益 (totalEq, {quote} 计价估算): {total_eq if total_eq is not None else 'N/A'}")

        typer.echo("")
        typer.echo("交易账户余额 (非零资产):")
        totals = balance.get("total") or {}
        free = balance.get("free") or {}
        used = balance.get("used") or {}
        non_zero: list[tuple[str, float]] = []
        for asset, amount in totals.items():
            try:
                amt = float(amount)
            except (TypeError, ValueError):
                continue
            if amt != 0.0:
                non_zero.append((asset, amt))
        non_zero.sort(key=lambda r: -abs(r[1]))
        if not non_zero:
            typer.echo("  (空)")
        else:
            typer.echo(f"  {'资产':<8} {'数量':>18} {'可用':>18} {'冻结':>18} {'USD 估值':>18}")
            for asset, amt in non_zero:
                usd_value = _quote_usd_value(adapter, asset, amt, quote)
                typer.echo(
                    f"  {asset:<8} {amt:>18.8f} "
                    f"{float(free.get(asset, 0) or 0):>18.8f} "
                    f"{float(used.get(asset, 0) or 0):>18.8f} "
                    f"{_format_usd(usd_value):>18}"
                )

        typer.echo("")
        typer.echo("资金账户余额 (非零资产):")
        try:
            funding_rows = adapter.fetch_funding_balance()
        except RuntimeError as exc:
            typer.echo(f"  (不可用: {exc})")
            funding_rows = []
        if not funding_rows:
            typer.echo("  (空)")
        else:
            typer.echo(f"  {'资产':<8} {'数量':>18} {'可用':>18} {'冻结':>18} {'USD 估值':>18}")
            for row in funding_rows:
                asset = row.get("ccy") or ""
                amt = float(row.get("total") or 0)
                usd_value = _quote_usd_value(adapter, asset, amt, quote)
                typer.echo(
                    f"  {asset:<8} {amt:>18.8f} "
                    f"{float(row.get('available') or 0):>18.8f} "
                    f"{float(row.get('frozen') or 0):>18.8f} "
                    f"{_format_usd(usd_value):>18}"
                )

        typer.echo("")
        typer.echo("持仓:")
        try:
            positions = adapter.fetch_positions()
        except Exception as exc:
            typer.echo(f"  (不可用: {exc})")
            positions = []
        open_positions = [
            p for p in positions
            if p.get("contracts") not in (None, 0, 0.0, "0", "")
        ]
        if not open_positions:
            typer.echo("  (无持仓)")
        else:
            for pos in open_positions:
                typer.echo(
                    f"  - {pos.get('symbol')} side={pos.get('side')} "
                    f"contracts={pos.get('contracts')} entry={pos.get('entryPrice')} "
                    f"upl={pos.get('unrealizedPnl')}"
                )
    finally:
        adapter.close()


@app.command("paper-orders")
def paper_orders(
    config: Path | None = _config_option(),
    exchange: str | None = _exchange_option("当前支持 okx"),
    symbol: str | None = typer.Option(None, help="可选交易对过滤"),
) -> None:
    """查询模拟盘未完成订单。"""

    project_config = _load_project_config(config)
    exchange = _resolve_exchange_name(project_config, exchange)
    _require_paper_trading_enabled(project_config, exchange)
    _require_private_credentials(project_config, exchange)
    adapter = create_exchange_adapter(exchange, _exchange_config_with_proxy(project_config, exchange))
    try:
        orders = adapter.fetch_open_orders(symbol=symbol, paper=True)
        typer.echo(json.dumps(orders, ensure_ascii=False, indent=2))
    finally:
        adapter.close()
