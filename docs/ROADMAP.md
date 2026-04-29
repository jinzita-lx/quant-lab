# Roadmap

> 该文档收录从 README 拆分出来的规划性内容，方便和"使用文档"分开维护。
> 如果你只想跑通项目，请回到 [README](../README.md)。

## 当前定位

第一阶段重点是建立一致的工程边界，而不是直接提供可实盘策略。
实盘所需的凭证、订单路由、风控阈值、监控告警和审计日志仍需要按交易团队要求继续补强。
未来可接入 `vectorbt`、`backtrader` 作为更成熟的研究或执行层，参考但不直接抄 `freqtrade` 的产品形态。

## 设计与规划文档

- [docs/codex-discussion.md](./codex-discussion.md) — 设计讨论总览
- [docs/deep-dive-discussion.md](./deep-dive-discussion.md) — 工程规划深入版（套利策略分类、SMA 之后值得补的非套利策略、Binance/OKX API 集成细节、收益验证方法论、风控与操作者工作流，以及对当前仓库的具体实现优先级建议）
- [docs/quant-lab-strategy-intro.md](./quant-lab-strategy-intro.md) — 策略层介绍
- [docs/quant-lab-usage.md](./quant-lab-usage.md) — 命令使用细节

## 推荐下一阶段里程碑

- 先补统一的交易对象模型：符号归一、现货/永续区分、交易所元数据和更严格的 CSV 数据约束
- 升级回测器：支持双腿套利、成本分项、延迟假设、walk-forward 和更完整的绩效指标
- 增加 paper trading / dry-run 层：落订单状态机、风控事件、部分成交和对账日志
- 再接 Binance/OKX 私有 REST 与后续 WebSocket，而不是直接跳到自动实盘
- 策略上优先补 breakout 与 mean reversion；套利方向先做严肃的跨所价差监控与模拟执行，再评估现货-永续基差 / funding carry

## 已知不足

- walk-forward 仅提供窗口切分与样本外验证骨架，不会自动重优化参数；如需参数重估，应在策略层增加训练窗口钩子或独立优化器
- OKX 模拟盘仅提供最小可用的下单与未完成订单查询链路，正式联调仍需要真实模拟盘 API Key / Secret / Passphrase
- 交易所适配器只实现了 Binance / OKX 的公共行情与少量私有端点；私有 REST 权限检测、重试、签名异常审计未覆盖

## 后续建议

- 将订单状态、资金曲线、风控事件落地到数据库或对象存储
- 引入异步事件总线，拆分行情、信号、执行、风控和告警
- 补充多策略组合层、资金分配层与实盘/模拟盘切换
- 为 Binance/OKX 的私有 API 增加权限检测、重试和签名异常审计
