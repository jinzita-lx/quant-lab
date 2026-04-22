# Crypto Quant Lab

一个面向 Python 的加密量化项目脚手架，覆盖以下最小能力：

- 配置加载与校验：`pydantic`
- CLI 入口：`typer`
- 交易所适配骨架：`ccxt`
- 回测与数据处理：`pandas`
- 测试入口：`pytest`

当前版本重点是建立一致的工程边界，而不是直接提供可实盘策略。实盘所需的凭证、订单路由、风控阈值、监控告警和审计日志仍需要按交易团队要求继续补强。未来可接入 `vectorbt`、`backtrader`、`freqtrade` 作为更成熟的研究或执行层。

## 前置条件

本项目使用 [uv](https://docs.astral.sh/uv/) 管理虚拟环境和依赖。如未安装：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

根据提示把 `~/.local/bin` 加入 `PATH`（或执行 `uv tool update-shell` 由 uv 自动处理）。

---

## 作为 CLI 工具安装（推荐给只想使用的人）

克隆仓库后在项目目录执行：

```bash
git clone git@github.com:jinzita-lx/quant-lab.git
cd quant-lab
uv tool install .
```

之后在任意目录下都可以直接调用 `quant-lab`，就像 `git`、`ls` 一样：

```bash
quant-lab --help
quant-lab show-config --config /path/to/configs/example.toml
quant-lab backtest --config /path/to/configs/example.toml --strategy btc_ma_cross
```

升级、卸载：

```bash
uv tool upgrade crypto-quant-lab   # 重新从本地代码编译安装
uv tool uninstall crypto-quant-lab # 卸载
```

注意：`uv tool install .` 会把当前代码**快照**打包安装到 uv 的工具目录（`~/.local/share/uv/tools/`），之后改源码**不会**自动生效，需要重新 `uv tool install --reinstall .`。如果你要改代码，请看下一节。

---

## 开发模式（推荐给要改代码 / 跑测试 / 添加策略的人）

克隆后用 `uv sync` 创建隔离环境并安装为**可编辑模式**（`-e`，改源码立即生效）：

```bash
git clone git@github.com:jinzita-lx/quant-lab.git
cd quant-lab
uv sync
```

这会自动：
- 创建 `.venv/`
- 按 `uv.lock` 锁定的版本装好所有依赖（含 dev 组，如 `pytest`）
- 把 `src/crypto_quant_lab/` 以 editable 方式装进去

之后所有命令用 `uv run` 在项目环境里执行，不需要手动激活：

```bash
uv run quant-lab show-config --config configs/example.toml
uv run quant-lab list-strategies --config configs/example.toml
uv run quant-lab backtest --config configs/example.toml --strategy btc_ma_cross
uv run quant-lab walk-forward --config configs/example.toml --strategy btc_ma_cross --train-size 20 --test-size 10
uv run pytest -q
```

如果你习惯传统方式，也可以激活虚拟环境后直接调用：

```bash
source .venv/bin/activate
quant-lab show-config --config configs/example.toml
pytest -q
deactivate
```

添加新依赖：

```bash
uv add ccxt-pro        # 加到主依赖
uv add --dev ipython   # 加到 dev 组
```

`uv add` 会自动更新 `pyproject.toml` 和 `uv.lock`，并把新包装进 `.venv/`。

如果你有自己的 OHLCV 数据，可以传入 CSV：

```bash
uv run quant-lab backtest --config configs/example.toml --strategy btc_ma_cross --csv /path/to/data.csv
```

CSV 需要至少包含：

- `timestamp`
- `close`

并满足以下规则：

- `timestamp` 必须能被解析为 UTC 时间
- `timestamp` 必须严格递增且唯一
- 时间戳必须按策略 `timeframe` 对齐，例如 `1m` 数据不能出现 `00:00:30`
- `close` 必须是有效数值

如果希望测试价差占位策略，可以提供：

- `timestamp`
- `close_primary`
- `close_secondary`

同样要求 `close_primary` 和 `close_secondary` 为有效数值，并且时间戳按该策略的 `timeframe` 对齐。

## 项目结构

```text
docs/
  codex-discussion.md
  deep-dive-discussion.md
configs/
  example.toml
src/crypto_quant_lab/
  backtest/
  exchanges/
  risk/
  strategies/
  cli.py
  config.py
  domain.py
tests/
```

## 主要命令

- `quant-lab show-config`：显示配置并脱敏敏感字段
- `quant-lab list-strategies`：列出配置中的策略
- `quant-lab backtest`：使用示例数据或 CSV 运行骨架回测
- `quant-lab walk-forward`：按训练窗口 / 测试窗口执行 walk-forward 回测
- `quant-lab quote`：通过 `ccxt` 访问交易所公开行情
- `quant-lab paper-order`：对 OKX 模拟盘提交订单
- `quant-lab paper-orders`：查询 OKX 模拟盘未完成订单
- `quant-lab account-info`：只读查询账户信息、余额、资金账户与持仓，并按计价币种折算 USD 估值

### Walk-forward 用法

```bash
uv run quant-lab walk-forward --config configs/example.toml --strategy btc_ma_cross --train-size 20 --test-size 10
```

可选参数 `--step-size N` 控制窗口滑动步长，默认等于 `--test-size`。若需要真实数据，可用 `--csv /path/to/data.csv` 传入。

**重要说明**：当前 walk-forward 只把训练窗口作为指标预热区间，**不会对策略参数再拟合**。如需真正的参数再拟合，应在策略层覆写对应训练钩子并在每个窗口调用。该命令的价值在于：用多个不重叠的未见测试窗口验证固定参数策略的稳定性，而不是代替参数搜索。

### OKX 模拟盘（Paper Trading）

OKX 官方模拟盘通过 HTTP header `x-simulated-trading: 1` 区分，与测试网是不同的机制。要使用这些命令：

1. 在 OKX 官网「模拟盘」页面生成一组专用的 API Key / Secret / Passphrase。
2. 在 shell 中导出为环境变量，变量名与 `configs/example.toml` 中的 `api_key_env` / `api_secret_env` / `password_env` 匹配：

   ```bash
   export OKX_API_KEY="<paper-api-key>"
   export OKX_API_SECRET="<paper-api-secret>"
   export OKX_API_PASSWORD="<paper-passphrase>"
   ```

3. 确认 `configs/example.toml` 中目标交易所配置已设置 `paper_trading = true`；未开启时 CLI 会直接拒绝执行以避免误伤实盘。

创建一笔模拟买单：

```bash
uv run quant-lab paper-order --config configs/example.toml --exchange okx --symbol BTC/USDT --side buy --amount 0.01
```

查看模拟盘未完成订单：

```bash
uv run quant-lab paper-orders --config configs/example.toml --exchange okx --symbol BTC/USDT
```

### 账户只读查询（account-info）

`account-info` 以只读方式查询一个交易所账户，并把结果按中文表格打印：

- 账户信息（id / type / label / uid）
- 总权益（`totalEq`，以计价币种估算）
- 交易账户余额（按非零资产过滤）
- 资金账户余额（OKX 提供，其他交易所会显示"不可用"）
- 每个资产的 USD 估值（通过 `fetch_ticker({asset}/{quote})` 折算，默认 `quote=USDT`；若某资产缺少对应行情，USD 估值列会落为 `N/A`）
- 持仓（衍生品；若无持仓则显示"(无持仓)"）

示例：

```bash
uv run quant-lab account-info --config configs/example.toml --exchange okx
```

可选参数：

- `--quote CCY`：切换 USD 估值所用的计价币种，默认 `USDT`

如果目标网络需要通过本地代理访问交易所，可以在运行命令前设置 shell 环境变量 `https_proxy` / `http_proxy`，或在对应交易所配置中显式填入 `https_proxy` 字段——`ExchangeConfig.resolved_https_proxy()` 会优先使用显式配置，其次回退到环境变量。该命令不会发起任何下单或撤单动作。

## 深入规划文档

- 深度讨论文档：[docs/deep-dive-discussion.md](docs/deep-dive-discussion.md)
- 设计讨论总览：[docs/codex-discussion.md](docs/codex-discussion.md)

`docs/deep-dive-discussion.md` 聚焦更细的工程规划，覆盖套利策略分类、SMA 之后值得补的非套利策略、Binance/OKX API 集成细节、收益验证方法论、风控与操作者工作流，以及对当前仓库的具体实现优先级建议。

## 推荐下一阶段里程碑

- 先补统一的交易对象模型：符号归一、现货/永续区分、交易所元数据和更严格的 CSV 数据约束
- 升级回测器：支持双腿套利、成本分项、延迟假设、walk-forward 和更完整的绩效指标
- 增加 `paper trading` / `dry-run` 层：落订单状态机、风控事件、部分成交和对账日志
- 再接 Binance/OKX 私有 REST 与后续 WebSocket，而不是直接跳到自动实盘
- 策略上优先补 `breakout` 与 `mean reversion`，套利方向先做严肃的跨所价差监控与模拟执行，再评估现货-永续基差 / funding carry

当前 walk-forward 仅提供窗口切分与样本外验证骨架，不会自动重优化参数；如果后续需要参数重估，应在策略层增加训练窗口钩子或独立优化器。OKX 模拟盘当前提供最小可用的下单与未完成订单查询链路，正式联调仍需要真实的模拟盘 API Key / Secret / Passphrase。

## 后续建议

- 将订单状态、资金曲线、风控事件落地到数据库或对象存储
- 引入异步事件总线，拆分行情、信号、执行、风控和告警
- 补充多策略组合层、资金分配层与实盘模拟盘切换
- 为 Binance/OKX 的私有 API 增加权限检测、重试和签名异常审计
