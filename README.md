# skill-b7-lhb-monitor · 龙虎榜监控 + 席位标签库

[![status](https://img.shields.io/badge/status-Community%20Project-blue)](https://github.com/quantskills/join/blob/main/COMMUNITY_RULES.md) [![license](https://img.shields.io/badge/license-GPL--3.0--only-green)](LICENSE)

> ⚠️ **Community Project（社区项目）**：本项目由社区成员创建，**未经 QuantSkills 官方审核 / 认证 / 背书**。
> **仅供量化研究与教育示例，不构成投资建议，不承诺任何收益。** 游资别名为民间观测映射、非券商官方身份、会迁移，
> **不构成对任何个人/机构的指认**。边界声明见文末。
> 声明文件 [SKILL.md](SKILL.md) ｜ English [README.en.md](README.en.md) ｜ 许可 [LICENSE](LICENSE)（GPL-3.0-only）

> 收盘后自动抓取 A 股龙虎榜，用**席位标签库**把营业部匹配成 北向/机构/游资/量化/营业部（覆盖率≈99%），
> 并接入**爬取的游资本尊库**（317 营业部 → 章盟主·作手新一·消闲派…+ 置信度）。
> 生成**次日关注清单**，每日整理**机构合集 / 营业部合集 / 个股详情页 / 区间统计**，出**交互式 HTML 看板**。
>
> **类型**：监控预警型 Skill ｜ **数据源**：PandaData ｜ **服务对象**：盘后复盘 agent · 游资情绪研究 · 人工复盘

---

## 一句话定位
**今天龙虎榜谁上榜、机构买了啥、哪个游资出手、明天关注谁。**

---

## 🔄 运行流程（一句话 → 落地结果）

```mermaid
flowchart TD
    Q["💬 用户：跑今天龙虎榜"] --> SK["skill 匹配 → 读 SKILL.md"]
    SK --> MD["maintain_daily(最近交易日)"]

    subgraph G1["① 抓取 (PandaData)"]
        F1["get_lhb_list<br/>异动股 + 上榜原因"]
        F2["get_lhb_detail<br/>买/卖席位明细 (全市场)"]
    end
    MD --> F1 & F2

    F2 --> TAG["② 席位标签匹配<br/>(优先级见下图)"]
    F1 --> AGG["③ 个股聚合<br/>多上榜原因拆分买卖营业部"]
    TAG --> AGG
    AGG --> WL["④ 次日关注清单打分<br/>机构净买·游资净买·买卖力量"]
    WL --> PARQ[("database.parquet<br/>个股行 + 汇总行")]

    PARQ --> R1["📋 每日整理<br/>机构合集/营业部合集"]
    PARQ --> R2["🖥️ 交互式 HTML 看板<br/>tab·搜索·筛选·排序·展开"]
    PARQ --> R3["🔍 个股详情页 / 区间统计"]
```

---

## 🏷️ 席位标签匹配优先级（核心逻辑）

```mermaid
flowchart TD
    A["营业部名 agency"] --> N{"含 沪/深股通专用?"}
    N -- 是 --> NB["🟦 北向"]
    N -- 否 --> I{"含 机构专用?"}
    I -- 是 --> INST["🟦 机构"]
    I -- 否 --> OV{"外部覆盖<br/>B7_SEAT_OVERRIDE 命中?"}
    OV -- 是 --> O["按覆盖标注"]
    OV -- 否 --> MAP{"爬取精确映射<br/>营业部全称命中?"}
    MAP -- 是 --> ALIAS["🟨 游资/量化<br/>+ 本尊alias + 帮派 + 置信度A/B/C"]
    MAP -- 否 --> SEED{"子串种子库命中?"}
    SEED -- 是 --> S["🟨 游资/量化 + 帮派"]
    SEED -- 否 --> BR{"含 营业部/分公司?"}
    BR -- 是 --> DESK["🟧 营业部<br/>(具名席位，游资盘计入)"]
    BR -- 否 --> P["⬜ 普通 (极少)"]
```

- **游资盘净买 `hotmoney_net` = 游资 + 营业部**（非机构/非北向/非量化的活跃资金）。
- 标签类型含"量化"（三板组/量化打板/量化基金、外资通道高盛/摩根/中金）→ 归 `量化`，**不计入游资盘**。
- 实测 6/23：245 个席位里仅 2 个落"普通"，68 个拿到真实游资本尊 alias。

---

## 💬 怎么说（自然语言触发）

| 你说 | 它做什么 |
|---|---|
| "跑一下今天龙虎榜" / "龙虎榜监控" | 抓榜 + 席位标签 + 次日清单 + 机构/营业部合集 |
| "明天关注哪些票" | 次日关注清单（打分排序 + 上榜理由） |
| "今天机构买了啥" | 机构合集（机构净买排序） |
| "章盟主 / 作手新一 / 宁波桑田路 今天买了哪些" | 营业部合集，按游资本尊/席位查标的 |
| "看下天娱数科的龙虎榜" | **个股详情页**：按上榜原因拆分，每原因列买入/卖出营业部表（带本尊标签、双金额） |
| "某票最近 3 天/这周区间统计" | **区间统计**：各营业部 总买/总卖/净额/上榜次数，按净额排序 |
| "出个龙虎榜 HTML 看板" | **交互式看板**：tab(股票/机构/营业部) · 搜索 · 筛选 · 列排序 · 点行展开详情 |
| "回填 6 月的龙虎榜" | 区间回填历史（区间统计依赖回填的历史） |

> 一只票一天可能有**多条上榜原因**（如同时涨幅偏离7% + 换手20%），每条原因对应各自一组买入/卖出营业部，详情页分别列出。

## ⚙️ 可选参数（不说走默认）

| 参数 | 默认 | 怎么说 |
|---|---|---|
| 日期 | 最近有数据交易日 | "看 6/18 的"（⏰ 龙虎榜傍晚才公布，**~19:30 后**跑） |
| 输出 | 看问法 | "口头答 / 给表格 / 出 HTML 看板" |
| 席位库 | 见下「席位标签库」 | 重爬刷新 / `B7_SEAT_OVERRIDE` 临时覆盖 |
| 打分权重 | 机构0.35 / 游资0.35 / 净买0.20 / 席位数0.10 | "更看重机构 / 更看重游资" |

---

## 🗃️ 席位标签库（核心资产，两层 + 可维护）

```mermaid
flowchart LR
    CSV["爬取CSV<br/>references/seat_data/*.csv"] -->|build_seat_map.py| MAP["seat_yyb_map.json<br/>317营业部→本尊+置信度"]
    SEED["seat_library.json<br/>~55席种子(帮派/级别)"] --> TAGS["seat_tags.match_seat"]
    MAP --> TAGS
    OVR["B7_SEAT_OVERRIDE<br/>(临时覆盖)"] --> TAGS
```

| 层 | 文件 | 内容 | 维护方式 |
|---|---|---|---|
| 爬取精确映射（主） | `scripts/seat_yyb_map.json` | 317 营业部全称 → 游资本尊 alias + 帮派 + 置信度A/B/C + 最近观测 | **重爬**：新 CSV 放 `references/seat_data/` → 跑 `build_seat_map.py` |
| 子串种子库（兜底） | `scripts/seat_library.json` | ~55 席（中信溧阳路·宁波桑田路·欢乐海岸·成都系…）按帮派/级别 | 直接改 JSON |
| 临时覆盖 | env `B7_SEAT_OVERRIDE` | `[{"match","category","tag",...}]` | 不改仓库即生效 |

> ⚠️ 游资别名是**民间观测映射、非券商官方身份、会迁移**——每条带 `confidence`(A/B/C) 与 `last_seen`，C-低不可单独当定论。仅供研究，不构成指认或投资建议。

---

## 📦 输出结构（落地 parquet）

主键 `(trade_date, build_id, target_id, result_type)`，两类行：

| result_type | 一行代表 | 关键字段 |
|---|---|---|
| `lhb_stock` | 一只上榜个股 | `is_watchlist`/`watchlist_rank`/`watch_reason` · `inst_net`/`hotmoney_net`/`north_net` · `n_reasons` · `result_json.reasons`(按上榜原因拆买卖营业部) · `result_json.buy_seats`(带本尊/帮派) |
| `lhb_summary` | 当日 1 行汇总 | `n_lhb` · `n_inst_buy` · `n_hotmoney_buy` · `n_watchlist` · `inst_net_total` |

- 结果落地：`生产产物/database.parquet`（追加合并）
- 看板样例：`生产产物/sample_lhb.html`

---

## ⌨️ 命令行（手动跑）

```bash
export PANDA_USERNAME=<86手机号>; export PANDA_PASSWORD=<密码>
python 开发产物/scripts/build.py --mode daily                 # 当日维护（⏰ ~19:30 后，龙虎榜才出）
python 开发产物/scripts/build.py --mode backfill --start 20260601 --end 20260618
python 开发产物/scripts/render.py                             # 每日整理（markdown）
python 开发产物/scripts/render.py --stock 002354.SZ           # 个股详情页（按上榜原因拆买卖营业部）
python 开发产物/scripts/render.py --stock 002354.SZ --range   # 个股区间统计
python 开发产物/scripts/render_html.py --out lhb.html         # 交互式 HTML 看板
python 开发产物/scripts/render_html.py --stock 002354.SZ --out r.html  # 个股区间统计 HTML
python 开发产物/scripts/build_seat_map.py                     # 重爬后刷新席位本尊库
python 开发产物/scripts/seat_tags.py                          # 自检席位标签库
```

---

## 🗂️ 目录

```text
build-b7-lhb-monitor/
├── README.md                 ← 你在这里
├── 开发产物/
│   ├── SKILL.md              · agent 调用规则 + 字段表
│   ├── skill.json            · 入口清单
│   ├── references/
│   │   ├── api_guide.md      · 接口口径 / 计算公式 / 席位库口径
│   │   └── seat_data/        · 原始爬取席位标签文档(.md/.csv，留档)
│   └── scripts/
│       ├── build.py          · 引擎：抓取/聚合/多上榜原因拆分/次日清单
│       ├── seat_tags.py      · 席位标签匹配（两层库 + 优先级）
│       ├── seat_library.json · 子串种子库
│       ├── seat_yyb_map.json · 爬取的营业部→本尊精确映射
│       ├── build_seat_map.py · CSV→映射 转换器（重爬刷新）
│       ├── render.py         · 每日整理/个股详情/区间统计(markdown)
│       ├── render_html.py    · 交互式 HTML 看板
│       └── test.py           · 单测（含真实数据冒烟）
└── 生产产物/
    ├── SKILL.md              · 生产读取规则
    └── database.parquet      · 结果（每日追加）
```

详细字段口径见 [开发产物/SKILL.md](开发产物/SKILL.md) 与 [开发产物/references/api_guide.md](开发产物/references/api_guide.md)。

---

## ⚠️ 边界与免责声明（社区规则 §4 / §8）

- **项目状态**：Community Project，未经 QuantSkills 官方审核 / 认证 / 验证 / 背书，非生产可用认证项目。
- **数据来源**：PandaData（`panda_data` ≥ 0.0.9）。
- **假设条件**：`net_buy` 为龙虎榜返回席位（买卖各 top5）净额，与部分行情软件"净买入"口径可能不同。
- **参数**：次日清单打分权重 / 关注 top-N 可配置。
- **已知限制**：龙虎榜傍晚才出（~19:30 后跑）；**游资别名为民间观测映射、非券商官方身份、会迁移**，
  每条带 `confidence`(A/B/C)/`last_seen`，C-低不可单独当定论。
- **风险边界**：输出为研究/复盘用的**客观统计与资金画像，不含买卖建议**。**不构成对任何个人/机构的指认。**
- **项目性质**：**仅供量化研究与教育示例，不构成投资建议，不承诺收益，不暗示策略安全或保证盈利。**
- **署名/许可**：四类席位逻辑借鉴 `capital_pricing/seat_analysis`（改为离线可复现）；席位本尊映射来自使用方爬取观测数据。许可证 **GPL-3.0-only**（[LICENSE](LICENSE)）。
- **维护者**：[@ZLHad](https://github.com/ZLHad)。

## 运行时入口（Runtime entrypoints）

本仓库按 QuantSkills 社区规则提供多运行时入口，均以根目录 [SKILL.md](SKILL.md) 为规范声明：

| 运行时 | 入口 |
|---|---|
| Claude Code / Codex | 根目录 `SKILL.md`（Codex 界面元数据见 [agents/openai.yaml](agents/openai.yaml)） |
| Cursor | [.cursor/rules/quantskills-skill.mdc](.cursor/rules/quantskills-skill.mdc)，完整规则见 [agents/cursor-rule.mdc](agents/cursor-rule.mdc) |
| Hermes / OpenClaw | [agents/portable-loader.md](agents/portable-loader.md)（便携加载提示） |
