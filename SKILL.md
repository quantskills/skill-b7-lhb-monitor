---
name: skill-b7-lhb-monitor
description: Monitor A-share Dragon-Tiger List activity and seat labels for research. Use when analyzing 龙虎榜 records, institutional participation, or related market signals; this is research-only material, not investment advice.
license: GPL-3.0-only
metadata:
  organization: QuantSkills
  organization_url: https://github.com/quantskills
  repository: skill-b7-lhb-monitor
  repository_url: https://github.com/quantskills/skill-b7-lhb-monitor
  project_type: skill
  collection: dragon-tiger-monitor
  license: GPL-3.0-only
---

# skill-b7-lhb-monitor · 龙虎榜监控 + 席位标签库（Dragon-Tiger Monitor）

> **项目状态：Community Project（社区项目）。** 本项目由社区成员创建，**未经 QuantSkills 官方审核、认证、验证或背书**，
> 也非生产可用认证项目。名称中的 `quantskills/` 仅表示托管组织，不代表任何官方身份。

A 股龙虎榜盘后监控工具：收盘后抓取龙虎榜，用席位标签库把营业部匹配成 北向/机构/游资/量化/营业部，
生成次日关注清单，每日整理机构合集 / 营业部合集 / 个股详情 / 区间统计，输出交互式 HTML 看板。

---

## 这个项目做什么（What）
把龙虎榜原始席位明细转成「带标签的资金画像 + 次日关注清单 + 每日整理视图」。

## 怎么用（How）
- 自然语言：对接 agent 后说"跑今天龙虎榜"（详见 [README.md](README.md)）。
- 命令行：`python 开发产物/scripts/build.py --mode daily`，再 `render_html.py` 出交互看板。
- 完整调用规则与字段表见 **[开发产物/SKILL.md](开发产物/SKILL.md)**（面向 agent 的详细声明）。

## 支持哪些场景（Scenarios）
盘后复盘 agent · 游资情绪类研究 · 人工复盘。

## 谁维护（Maintainer）
社区成员 [@ZLHad](https://github.com/ZLHad)。Issues / PR 欢迎。

## 重要限制（Limitations）
- 龙虎榜傍晚才公布，需 **~19:30 后**运行。
- **席位—游资别名是民间观测映射、非券商官方身份、会随时间迁移**；每条带 `confidence`(A/B/C) 与 `last_seen`，
  C-低不可单独当定论。**本库不构成对任何个人/机构的指认。**
- 依赖 PandaData 账号与流量额度。

---

## 量化项目边界声明（社区规则 §8）
- **数据来源**：PandaData（`panda_data` ≥ 0.0.9）；`get_lhb_list` / `get_lhb_detail` / `get_stock_detail`。
- **假设条件**：`net_buy` 为龙虎榜返回席位（买卖各 top5）净额，与部分行情软件"净买入"口径可能不同；席位分类见 api_guide。
- **参数**：次日清单打分权重、关注 top-N 可配置。
- **已知限制**：见上「重要限制」；游资别名为民间映射，需结合置信度/最近观测使用。
- **风险边界**：输出为**研究/复盘用的客观统计与资金画像，不含买卖建议**。
- **项目性质**：**仅供量化研究与教育示例**，不构成投资建议，不承诺任何收益，不暗示策略安全或保证盈利。

## 署名与许可（社区规则 §3 / §6）
- 许可证：**GPL-3.0-only**（见 [LICENSE](LICENSE)）。
- 四类席位分类逻辑借鉴自本地 `capital_pricing/seat_analysis`，改为离线可复现实现（不依赖在线 AI）。
- 席位本尊映射来自使用方爬取整理的观测数据（存 `开发产物/references/seat_data/`），**非券商官方身份**，仅供研究。
- 第三方依赖：`panda_data`、`pandas`、`numpy`、`pyarrow`，均遵循各自许可证。

English declaration: see [README.en.md](README.en.md).
