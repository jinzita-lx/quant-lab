# quant-lab 使用指南

本文面向日常使用 `quant-lab` 命令行的研究员与工程师，覆盖当前仓库真实落地的能力（配置、回测、walk-forward、行情快照、模拟盘下单与查询、账户只读查询）。内容仅反映现有代码，不包含未实现的特性。

## 1. 环境准备

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

安装完成后应能调用 `quant-lab` 命令，入口定义在 `pyproject.toml` 的 `[project.scripts]`。

## 2. 配置文件

示例配置位于 `configs/example.toml`，主要段落：

- `[app]`：默认交易所、计价币种等全局设置
- `[backtest]`：初始资金、费率、滑点、时间粒度
- `[risk]`：最大仓位名义值、单日最大回撤、止盈止损等风控参数
- `[exchanges.<name>]`：交易所凭证环境变量名、`testnet` / `paper_trading` / `https_proxy` 等
- `[[strategies]]`：策略条目，`kind` 指定策略类型，`params` 为策略参数

加载路径：`crypto_quant_lab.config.load_config(Path)`，使用 Pydantic v2 做强校验，未知字段会直接报错（`extra="forbid"`）。

### 凭证与代理

- 私有 API 凭证通过环境变量注入，变量名在配置里显式声明（`api_key_env` / `api_secret_env` / `password_env`），配置文件本身不保存明文。
- 如果访问交易所需要经本地代理：
  - 方式 A：在 shell 中导出 `https_proxy`、`http_proxy`。
  - 方式 B：在交易所配置块中显式填入 `https_proxy = "<proxy-url>"`。
  - `ExchangeConfig.resolved_https_proxy()` 会先取显式配置，再回退到环境变量。

## 3. 常用命令

### 查看配置

```bash
quant-lab show-config --config configs/example.toml
```

以 JSON 打印加载后的配置，对 `api_key` / `api_secret` / `password` 做脱敏。

### 列出策略

```bash
quant-lab list-strategies --config configs/example.toml
```

### 回测

```bash
quant-lab backtest --config configs/example.toml --strategy btc_ma_cross
```

- 未传 `--csv` 时使用内置的合成样本数据（单腿策略走 OHLCV 样本，套利策略走双腿价差样本）。
- 传入 `--csv /path/to/data.csv` 时，会按策略声明的 `required_market_data_columns` 和 `timeframe` 做校验：
  - `timestamp` 必须可解析为 UTC 且严格递增、唯一
  - 时间戳间隔必须与策略 `timeframe` 对齐（例如 `1m` 数据不能出现 `00:00:30`）
  - 数值列必须是有效数字

### Walk-forward 回测

```bash
quant-lab walk-forward --config configs/example.toml --strategy btc_ma_cross \
  --train-size 20 --test-size 10
```

- 按训练窗口 / 测试窗口滑动切分，并为每个测试窗口单独输出 `return_pct`、`net_pnl` 等指标。
- 可选 `--step-size N` 控制窗口滑动步长，默认等于 `--test-size`。
- **重要**：当前实现只把训练窗口作为指标预热区间，**不会自动重拟合策略参数**。它的价值在于用多个样本外窗口验证固定参数策略稳定性，而非替代参数搜索。

### 公共行情

```bash
quant-lab quote --config configs/example.toml --exchange okx --symbol BTC/USDT
```

调用 ccxt `fetch_ticker` 并以 JSON 形式输出 `TickerSnapshot`。

### OKX 模拟盘下单

前置条件：
1. 在 OKX 官网"模拟盘"页面生成专用 API Key / Secret / Passphrase。
2. 在 shell 中导出对应环境变量（变量名来自配置的 `*_env` 字段）。
3. 确认目标交易所配置中 `paper_trading = true`，否则 CLI 会直接拒绝执行，避免误触实盘。

```bash
quant-lab paper-order --config configs/example.toml --exchange okx \
  --symbol BTC/USDT --side buy --amount 0.01
```

`paper-order` 会在请求中附带 `tdMode=cash` 与 `x-simulated-trading=1`，配合 `set_sandbox_mode(True)` 走 OKX 模拟盘。

查询未完成订单：

```bash
quant-lab paper-orders --config configs/example.toml --exchange okx --symbol BTC/USDT
```

### 账户只读查询（account-info）

```bash
quant-lab account-info --config configs/example.toml --exchange okx
```

命令以只读方式调用 ccxt 的 `fetch_accounts` / `fetch_balance` / `fetch_positions`，并对 OKX 额外调用 `private_get_asset_balances` 取资金账户。输出分区（均为中文）：

- `账户信息`：账户 id / type / label / uid
- `总权益`：来自 `fetch_balance` 返回的 `info.data[0].totalEq`，以计价币种估算
- `交易账户余额 (非零资产)`：按数量降序列出资产的数量 / 可用 / 冻结 / USD 估值
- `资金账户余额 (非零资产)`：OKX 提供；非 OKX 会显示"(不可用: ...)"
- `持仓`：衍生品持仓；无持仓显示"(无持仓)"

USD 估值通过 `fetch_ticker(f"{asset}/{quote}")` 即时折算，`quote` 默认 `USDT`，可用 `--quote CCY` 切换。无法拉到行情时单元格会落为 `N/A`，不会中断整条命令。

该命令不会发起任何下单 / 撤单请求。

## 4. 开发流程

- 运行测试：`pytest`
- 项目测试 pythonpath 已在 `pyproject.toml` 配成 `["src"]`，可直接执行。
- 新加功能建议遵循：先写失败测试 → 跑测试确认红 → 最小实现让测试转绿 → 必要时再补文档。

## 5. 已知边界

- 回测器、walk-forward 目前走简化模型（固定头寸、简单费率、样本数据支撑），不适合直接替代专业回测平台。
- 交易所适配器只实现了 Binance / OKX 的公共行情与少量私有端点；私有 REST 权限检测、重试、签名异常审计未覆盖。
- 没有事件总线、持仓数据库与多策略组合层，这些仍属于后续规划。

更多后续方向见 `docs/deep-dive-discussion.md`。
