# quant-lab 策略介绍

本文说明当前仓库中真实落地的策略类型、触发逻辑、依赖的市场数据结构与参数，以便在配置 `configs/example.toml` 或扩展自定义策略时有明确的基线。目前 `crypto_quant_lab.strategies` 模块提供两类策略：

| kind | 类名 | 定位 |
| --- | --- | --- |
| `moving_average` | `SimpleMovingAverageStrategy` | 单腿趋势追踪：基于短/长期均线的交叉信号 |
| `spread_arbitrage` | `SpreadArbitrageStrategy` | 双腿跨交易所价差：基于 bps 阈值的入场 / 退出 |

两者都继承自 `BaseStrategy`，共享：

- `name` / `symbol` / `timeframe` 由 `StrategyConfig` 注入
- `required_market_data_columns()` 声明需要的列，回测器会据此做 CSV 校验
- `generate_signal(market_data)` 返回 `StrategySignal`，可能的 action 来自 `SignalAction` 枚举（`BUY` / `SELL` / `HOLD` / `ENTER_SPREAD` / `EXIT_SPREAD`）

## 1. 简单均线策略：`moving_average`

实现：`src/crypto_quant_lab/strategies/moving_average.py`

### 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `short_window` | 5 | 短期均线窗口长度（根数） |
| `long_window` | 20 | 长期均线窗口长度（根数） |

`warmup_period()` 返回 `long_window`，供回测器跳过预热期、从第 `long_window` 根开始参与交易决策。

### 所需市场数据

列：`timestamp`, `close`

- `timestamp` 必须可解析为 UTC，严格递增、无重复
- `close` 必须为有效数值
- 时间戳间隔必须与 `timeframe` 对齐

### 触发逻辑

在最新一根上对比：

- `prev_short <= prev_long` 且 `curr_short > curr_long` → `BUY`（短期均线上穿长期均线）
- `prev_short >= prev_long` 且 `curr_short < curr_long` → `SELL`（短期均线下穿长期均线）
- 其他情况 → `HOLD`

样本不足 `long_window` 时直接返回 `HOLD`，原因写入 `StrategySignal.reason`。

### 适用场景与局限

- 适合用来跑通端到端的信号 → 回测 → 报表链路，或作为基准对照。
- 只依赖 `close`，不感知波动率 / 成交量 / 资金费率，不适合直接实盘。
- 没有仓位叠加逻辑，BUY/SELL 仅代表方向变化，头寸管理由回测器 / 风控层决定。

## 2. 价差套利策略：`spread_arbitrage`

实现：`src/crypto_quant_lab/strategies/spread_arbitrage.py`

### 参数

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `buy_exchange` | — | 建多腿交易所名称（配置用，逻辑层不再校验） |
| `sell_exchange` | — | 建空腿交易所名称 |
| `primary_price_column` | `close_primary` | 主腿（买方）在行情数据中的价格列名 |
| `secondary_price_column` | `close_secondary` | 副腿（卖方）在行情数据中的价格列名 |
| `entry_spread_bps` | 8.0 | 价差达到该阈值（bps）则触发入场 |
| `exit_spread_bps` | 3.0 | 价差回落到该阈值（bps）则触发退出 |

### 所需市场数据

列：`timestamp`, `primary_price_column`, `secondary_price_column`

例如默认列名下，CSV 需要同时提供 `close_primary` 和 `close_secondary`。数值校验与对齐规则与均线策略一致。

### 触发逻辑

以最新一根 bar 为准：

```
spread_bps = (secondary_price - primary_price) / primary_price * 10000
```

- `spread_bps >= entry_spread_bps` → `ENTER_SPREAD`（价差足够大，入场套利）
- `spread_bps <= exit_spread_bps` → `EXIT_SPREAD`（价差收敛到阈值以下，退出）
- 其他区间 → `HOLD`

`spread_bps` 的当前值会写入 `StrategySignal.metadata`，便于在回测日志或下游监控查看。

### 适用场景与局限

- 适合作为跨所价差策略的"信号骨架"，验证数据对齐、时区处理、阈值触发链路。
- **不包含真实执行层**：没有对冲成交腿的下单逻辑、未处理延迟 / 部分成交 / 交易所间资金拨付。
- 费率、滑点、换手成本统一交由回测器在成本段处理，当前实现不区分吃单 / 挂单差异。
- 想做真正的资金费率 / 基差 / 三角套利，需要额外的信号组件与执行模块。

## 3. 配置示例

`configs/example.toml` 中的两段策略条目：

```toml
[[strategies]]
name = "btc_ma_cross"
kind = "moving_average"
symbol = "BTC/USDT"
exchange = "binance"
timeframe = "1h"

[strategies.params]
short_window = 5
long_window = 20

[[strategies]]
name = "btc_okx_binance_spread"
kind = "spread_arbitrage"
symbol = "BTC/USDT"
exchange = "binance"
timeframe = "1m"

[strategies.params]
buy_exchange = "binance"
sell_exchange = "okx"
primary_price_column = "close_primary"
secondary_price_column = "close_secondary"
entry_spread_bps = 8.0
exit_spread_bps = 3.0
```

## 4. 扩展新策略的最小步骤

1. 在 `src/crypto_quant_lab/strategies/` 下新增子类，继承 `BaseStrategy`，实现：
   - `kind` 字段（字符串，和配置中 `kind` 对齐）
   - `required_market_data_columns()`
   - 可选的 `warmup_period()`（默认 0）
   - `generate_signal(market_data) -> StrategySignal`
2. 在 `crypto_quant_lab.strategies.__init__.build_strategy` 的 `mapping` 中注册 kind → 类。
3. 在 `tests/` 下为新策略加单元测试：构造最小行情样本，断言信号 action / reason / metadata。
4. 必要时在 `configs/example.toml` 里追加一条示例配置。

## 5. 下一阶段值得考虑的策略方向

以下方向仓库尚未实现，但与现有脚手架兼容：

- **Breakout**：基于区间高低点突破的趋势触发器，适合在 MA 之外做对比组。
- **Mean reversion**：基于布林带 / z-score 的均值回归策略。
- **Funding / 基差**：永续资金费率、现货-永续基差；需先补完交易所元数据（已有 `MarketType` 区分 spot / perpetual）。
- **跨所严肃价差监控**：在现有 `spread_arbitrage` 骨架之上加真正的执行模拟（延迟、部分成交、资金腿调拨）。

扩展这些策略时，优先让"信号层"干净独立，把成本、风控、执行的真实性问题留在回测器 / 风控模块里处理，保持每一层的职责边界清晰。
