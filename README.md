# Crypto Quant Lab

面向 Python 的加密量化项目脚手架：配置加载（pydantic）、CLI（typer）、交易所适配（ccxt）、回测（pandas）、测试（pytest）。

> 本仓库定位是**工程脚手架**，不是开箱即用的实盘策略。规划与里程碑见 [docs/ROADMAP.md](docs/ROADMAP.md)。

## Quickstart

需要 [uv](https://docs.astral.sh/uv/)。装好之后：

```bash
git clone git@github.com:jinzita-lx/quant-lab.git
cd quant-lab
uv sync                               # 创建 .venv 并安装依赖（含 dev）

uv run quant-lab --version
uv run quant-lab list-strategies      # 用 configs/default.toml 跑通公开命令
uv run quant-lab backtest --strategy btc_ma_cross
uv run pytest -q
```

要查询账户/下模拟盘订单，再做一次性凭证准备，见下方 [凭证](#凭证okx-模拟盘).

---

## 安装

### 仅使用（不改代码）

```bash
uv tool install .
quant-lab --help
```

`uv tool install .` 是**快照安装**，源码改动不会自动生效，需要 `uv tool install --reinstall .`。

升级 / 卸载：

```bash
uv tool upgrade crypto-quant-lab
uv tool uninstall crypto-quant-lab
```

### 修改代码（贡献者）

```bash
uv sync           # 装到 .venv，editable 模式
uv run pytest -q
```

`uv sync` 会按 `uv.lock` 锁定版本。新增依赖：

```bash
uv add ccxt-pro          # 主依赖
uv add --dev ipython     # dev 依赖
```

---

## 配置

CLI 默认读取 `./configs/default.toml`。两份配置：

| 文件 | 用途 |
|---|---|
| `configs/default.toml` | 项目实际使用的默认配置，CLI 默认 fallback |
| `configs/example.toml` | 纯净模板，凭证字段留空。复制改名后即可作为个人配置 |

显式指定其他配置：

```bash
# --config 是子命令选项，必须写在子命令之后
quant-lab show-config --config /path/to/my.toml

# 也可以用环境变量，所有命令一次生效
export QUANT_LAB_CONFIG=/path/to/my.toml
quant-lab show-config
```

### 环境变量

| 变量 | 作用 | 默认 / 来源 |
|---|---|---|
| `QUANT_LAB_CONFIG` | 配置文件路径 | `./configs/default.toml` |
| `QUANT_LAB_EXCHANGE` | 私有命令使用的交易所 | `config.app.default_exchange` |
| `OKX_API_KEY` / `OKX_API_SECRET` / `OKX_API_PASSWORD` | OKX 模拟盘凭证 | 见下一节 |
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | Binance 私钥（如启用） | 无 |
| `https_proxy` / `HTTPS_PROXY` / `http_proxy` / `HTTP_PROXY` | 出网代理 | 推荐在配置文件中显式写 `https_proxy` / `http_proxy`（见下方排错），仅在没填时回退到环境变量 |

### 凭证（OKX 模拟盘）

OKX 模拟盘通过 HTTP header `x-simulated-trading: 1` 区分，与测试网是不同机制。三步：

1. 在 OKX 官网「模拟盘」生成专用 API Key / Secret / Passphrase
2. 把凭证放进项目根的 `.okx_demo_env`（推荐）或在 shell 中 `export`
3. 确认配置中目标交易所有 `paper_trading = true`（`example.toml` 已默认开启）

`.okx_demo_env` 自动加载：

```bash
cp .okx_demo_env.example .okx_demo_env
# 编辑 .okx_demo_env 填入真实凭证
```

CLI 启动时会自动从项目根读取并填入环境变量。**已有的 shell 环境变量优先级更高，不会被覆盖。**

> ⚠️ **安全提示**：`.okx_demo_env` 已在 `.gitignore` 中。**不要 commit 真实凭证**。仓库里只允许提交 `.okx_demo_env.example`。

---

## 命令参考

```bash
quant-lab --help
quant-lab --version          # 等价于 quant-lab version
```

### 公开命令（无需凭证）

| 命令 | 作用 |
|---|---|
| `show-config` | 打印配置（脱敏） |
| `list-strategies` | 列出已配置策略 |
| `quote --symbol BTC/USDT` | 公共行情快照 |
| `backtest --strategy <name>` | 用示例数据或 CSV 跑骨架回测 |
| `walk-forward --strategy <name> --train-size N --test-size M` | 滑动窗口样本外回测 |

示例：

```bash
uv run quant-lab backtest --strategy btc_ma_cross
uv run quant-lab walk-forward --strategy btc_ma_cross --train-size 20 --test-size 10
uv run quant-lab quote --symbol ETH/USDT
```

`walk-forward` 当前**不重新拟合参数**，只用训练窗口预热指标，再用测试窗口做样本外验证。需要参数搜索得自己加。

### 私有命令（需要凭证）

| 命令 | 作用 |
|---|---|
| `account-info` | 只读：账户信息、交易/资金账户余额、持仓、USD 估值 |
| `paper-order` | OKX 模拟盘下单 |
| `paper-orders` | OKX 模拟盘未完成订单 |

示例（默认使用 `config.app.default_exchange = okx`，无需 `--exchange`）：

```bash
uv run quant-lab account-info
uv run quant-lab account-info --quote USDC
uv run quant-lab paper-order --symbol BTC/USDT --side buy --amount 0.01
uv run quant-lab paper-orders --symbol BTC/USDT
```

`paper-order` 默认市价单；限价单加 `--order-type limit --price 70000`。
`account-info` 只调用只读 API，不会下单或撤单。

### 自定义 CSV 数据

`backtest` / `walk-forward` 可传 `--csv /path/to/data.csv` 替代示例数据：

- 必备列：`timestamp`、`close`
- 价差套利策略改用：`timestamp`、`close_primary`、`close_secondary`
- `timestamp` 必须可解析为 UTC，严格递增且唯一，并按策略 `timeframe` 对齐（例如 `1m` 数据不能出现 `00:00:30`）
- 价格列必须是有效数值

---

## 排错（FAQ）

**Q: 跑 `account-info` 报 `binance fetchAccounts() is not supported yet`**
A: 默认交易所被设置成了 binance，但 ccxt 的 binance 不支持 `fetch_accounts`。把 `config.app.default_exchange` 改成 `okx`，或运行时 `--exchange okx`。

**Q: 报 `交易所 okx 缺少凭证：OKX_API_KEY、...`**
A: CLI 没读到凭证。用 `.okx_demo_env`（推荐）或在当前 shell `export` 三个变量。

**Q: 网络超时 / 访问交易所失败（要走代理）**
A: 推荐在配置文件的 `[network]` 段写一份**项目级公共代理**，所有交易所共享：

```toml
[network]
https_proxy = "http://127.0.0.1:7890"
http_proxy  = "http://127.0.0.1:7890"   # 可选；不写时复用 https_proxy
```

如果某个交易所要走**不同的代理**，再在该交易所块下覆盖：

```toml
[exchanges.some_special_exchange]
# ...
https_proxy = "http://10.0.0.1:1080"
```

优先级（从高到低）：`exchanges.<name>.https_proxy` → `[network].https_proxy` → 环境变量 `https_proxy` / `HTTPS_PROXY`（http 同理）。
缺一边时，http 会自动复用 https 设置。

**Q: `uv tool install` 装的版本改源码不生效**
A: 这是快照安装。改完 `uv tool install --reinstall .`，或改用 `uv sync` + `uv run` 的开发模式。

**Q: 怎么单跑测试？**
A: `uv run pytest -q`，或激活 venv 后 `pytest -q`。

---

## 项目结构

```text
configs/
  default.toml          # CLI 默认配置
  example.toml          # 模板
src/crypto_quant_lab/
  cli.py                # CLI 入口（typer）
  config.py             # 配置模型（pydantic）
  domain.py             # 通用领域类型（如 InstrumentId）
  backtest/             # 回测引擎、walk-forward、示例数据
  exchanges/            # ccxt 适配
  risk/                 # 风控
  strategies/           # 策略
tests/                  # pytest
docs/                   # 设计/规划/使用文档
.okx_demo_env.example   # 凭证模板（复制为 .okx_demo_env 后填值）
```

---

## 进一步阅读

- [docs/quant-lab-usage.md](docs/quant-lab-usage.md) — 命令使用细节
- [docs/quant-lab-strategy-intro.md](docs/quant-lab-strategy-intro.md) — 策略层介绍
- [docs/ROADMAP.md](docs/ROADMAP.md) — 规划、里程碑、已知不足
- [docs/codex-discussion.md](docs/codex-discussion.md) / [docs/deep-dive-discussion.md](docs/deep-dive-discussion.md) — 设计讨论
