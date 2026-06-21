---
name: build-b7-lhb-monitor
description: 当需要收盘后自动抓取 A 股龙虎榜、用席位标签库匹配营业部(机构/北向/游资/量化)、生成次日关注清单并做每日整理(机构合集/游资席位合集)与可视化时，使用此 skill。该 BUILD 可被复盘 agent 或 Alpha 调用。
tags: [quant, build, development, monitor, dragon-tiger, seat]
---

# 龙虎榜监控 + 席位标签库 BUILD（B7）

## 工具定位

- 工具类型：监控预警型 BUILD
- 解决问题：把龙虎榜原始席位明细转成「带标签的资金画像 + 次日关注清单 + 每日整理视图」
- 使用对象：盘后复盘 agent / 游资情绪类 Alpha / 人工复盘

## 适用场景

- 收盘后想要「今天龙虎榜谁上榜、机构买了啥、哪些知名游资出手、明天关注谁」
- Alpha 需要稳定的 `inst_net` / `hotmoney_net` / 席位分类输入而不想各自重算
- 人工想看「机构合集」「某游资席位今天买了哪些票」

## 核心能力（四件套）

| 能力 | 实现 | 说明 |
|---|---|---|
| 收盘后抓取龙虎榜 | `fetch_lhb` | `get_lhb_list`(异动股) + `get_lhb_detail`(买/卖席位，全市场) |
| 匹配席位标签 | `seat_tags.match_seat` | 营业部 → 北向/机构/游资/量化/普通 + 席位俗称（确定性规则 + 可维护种子库 + 外部覆盖） |
| 生成次日关注清单 | `compute_watchlist` | 机构净买 / 知名游资净买 / 买卖力量 / 知名席位数 综合打分排序 |
| 每日整理 + 可视化 | `render` / `render_html` | 机构合集 / 游资席位合集 / 个股席位明细 / 暗色 HTML 看板 |

## 席位标签库（核心资产，`seat_tags.py`）

- 北向 / 机构：确定性关键词（`沪深股通专用` / `机构专用`），零歧义。
- 游资 / 量化：`SEAT_LIBRARY` 种子库（子串匹配，~33 条知名活跃席位：中信溧阳路、宁波桑田路、
  华泰益田路荣超、东财拉萨系、欢乐海岸、成都系、温州帮…）。
- 外部覆盖：环境变量 `B7_SEAT_OVERRIDE` 指向 JSON `[{"match","category","tag","note"}]`，优先于内置库。
- ⚠️ 种子库是「起点」，席位—游资对应会随时间变动，使用方须持续核对；不构成对个人/机构的指认。

## 输入

输入来自 PandaData 龙虎榜接口，或调用方传入的标准结构化席位数据。

`run()` 接受两种形态：
1. `dict{list, buy, sell}`（`fetch_lhb` 的输出形态，各为 records / DataFrame）。
2. 席位明细 records（含 `ts_code`/`symbol` + `agency` + `side` + `b_value`/`s_value`）。

| 字段 | 类型 | 必须 | 说明 |
|---|---|---|---|
| ts_code/symbol | string | 是 | 股票代码 |
| agency | string | 是 | 营业部名称（席位标签匹配用） |
| side | string | 否 | buy / sell（缺省视为 buy） |
| b_value / s_value | float | 否 | 买入 / 卖出金额 |
| rank / reason | - | 否 | 龙虎榜排名 / 上榜原因 |

## 输出

标准化面板（BUILD 规则 §11 兼容）。主键 `(trade_date, build_id, target_id, result_type)`。

| 字段 | 类型 | 说明 |
|---|---|---|
| trade_date / build_id / build_name | string | 日期 / `B7` / `龙虎榜监控+席位标签库` |
| target_id / ts_code / name / board_type | string | 标的 |
| result_type | string | `lhb_stock`(个股行) / `lhb_summary`(每日 1 行 MARKET 汇总) |
| result_value | string | `次日关注` / `上榜`；MARKET 行为 `N上榜/M关注` |
| is_watchlist / watchlist_rank / score / watch_reason | bool/int/float/string | 次日关注清单 |
| net_buy / inst_net / hotmoney_net / north_net / quant_net | float | 总/机构/游资/北向/量化 净买额 |
| known_seat_cnt / n_reasons / top_buy_seat | int/int/string | 知名席位数 / 当日上榜原因条数 / 最大买入席位 |
| type / reason / amount / change_rate / turnover | - | 上榜原因 / 金额 / 涨跌幅 / 换手 |
| result_json | string | 全状态 JSON；MARKET 行存汇总 dict |
| data_version / update_time | string | 版本 / 生成时间 |

`result_json`（个股行）关键结构：
- `buy_seats` / `sell_seats`：席位明细（聚合跨原因），每席位带 `b`(买)/`s`(卖)/`category`/`tag`。
- `reasons`：**按上榜原因拆分**的数组——一票一天可有多条原因，每条 `{type, reason, buy:[席位], sell:[席位], buy_total, sell_total}`，对应个股详情页。
- `n_reasons`：上榜原因条数。

> 读取时按 `result_type` 区分：个股 `df[df.result_type=="lhb_stock"]`，汇总 `df[df.result_type=="lhb_summary"]`。

## 调用方式

```python
# 模式 A：调用型——调用方已有龙虎榜数据
from scripts.build import run
panel = run({"list": [...], "buy": [...], "sell": [...]}, config={"names": {...}})

# 模式 B：每日维护——自动抓取 + 标签 + 次日清单
from scripts.build import maintain_daily, save_parquet
panel = maintain_daily("2026-06-19")
save_parquet(panel)                         # 追加合并进 生产产物/database.parquet

# 模式 C：区间回填
from scripts.build import backfill, save_parquet
save_parquet(backfill("2026-06-01", "2026-06-19"))

# 展示
from scripts.render import render_markdown, render_stock_detail, render_range_stats
from scripts.render_html import render_html, render_range_html
md = render_markdown(panel)                          # 每日整理
detail = render_stock_detail(panel, "002354.SZ")     # 个股详情页（按上榜原因拆买卖营业部）
rng = render_range_stats(panel, "002354.SZ")         # 个股区间统计（各营业部总买/总卖/净额）
html = render_html(panel)                            # 交互式看板（tab/搜索/筛选/排序/展开详情）

# 区间统计（从落地的 parquet 历史聚合）
from scripts.build import range_stats
rs = range_stats(panel, "002354.SZ", start="20260601", end="20260618")
```

命令行：

```bash
export PANDA_USERNAME=<86手机号>; export PANDA_PASSWORD=<密码>
python scripts/build.py --mode daily --date 20260619
python scripts/build.py --mode backfill --start 20260601 --end 20260619
python scripts/render.py --stock 002354.SZ                  # 个股详情页（markdown）
python scripts/render.py --stock 002354.SZ --range          # 个股区间统计
python scripts/render_html.py --date 2026-06-19 --out lhb.html        # 交互式看板
python scripts/render_html.py --stock 002354.SZ --out r.html          # 区间统计 HTML
python scripts/seat_tags.py                 # 自检席位标签库
```

## Agent 执行规则（含 Q&A）

1. 调用方已有龙虎榜数据 → 优先 `run(...)`，不重复抓取。
2. 每日生产维护用 `maintain_daily()` + `save_parquet()`，供他人直接读，不重算。
3. **Agent 问答**：读 `database.parquet` 按 `result_type` 拆分后用 pandas 回答：
   - 「今天机构买了啥」→ `df[df.inst_net>0].sort_values("inst_net")`
   - 「XX游资今天买了哪些」→ 解析 `result_json.buy_seats`，按 `tag` 过滤
   - 「明天关注谁」→ `df[df.is_watchlist].sort_values("watchlist_rank")`
   - 「龙虎榜整体」→ 读 `lhb_summary` 行的 `result_json`
   回答时注明席位标签来自可维护种子库，需结合实际席位核对。
4. 必须先 `python scripts/test.py` 全绿；真实数据因配额/权限会自动跳过（不判失败）。

## 可被 Alpha 调用

- 是
- 调用限制：输入须含 `ts_code/symbol` + `agency`
- 依赖数据：龙虎榜列表 + 买/卖席位明细

## 是否需要生产结果

- 是否生成 `database.parquet`：是（结果型，盘后统一计算，多人复用）
- 更新频率：每日收盘后 `maintain_daily()` 追加
- 字段结构：见 `../生产产物/SKILL.md`

## 依赖

- panda_data ≥ 0.0.9（`get_lhb_list` / `get_lhb_detail` / `get_stock_detail` / `get_trade_cal`）
- pandas、numpy、pyarrow
- 凭证环境变量：`PANDA_USERNAME` / `PANDA_PASSWORD`（兼容 `PANDA_DATA_*`）
- 可选 `B7_SEAT_OVERRIDE`：席位标签外部覆盖 JSON
