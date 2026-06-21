---
name: build-b7-lhb-monitor-production
description: 当需要读取龙虎榜监控+席位标签库（B7）的生产结果时，使用此 skill。读取已生成的 Parquet 龙虎榜历史与次日关注清单，不重复抓取与重算。
tags: [quant, build, production, monitor, dragon-tiger, seat]
---

# 龙虎榜监控+席位标签库生产结果（B7）

## 工具定位

- 工具类型：结果型 BUILD
- 服务对象：盘后复盘 agent / 游资情绪 Alpha / 人工复盘
- 是否可被 Alpha 调用：是

## 结果文件

- 文件路径：`database.parquet`
- 数据格式：Parquet
- 更新频率：每日收盘后，由开发产物 `maintain_daily()` 生成并 `save_parquet()` 追加
- 生成任务：`python build-b7-lhb-monitor/开发产物/scripts/build.py --mode daily --date <交易日>`
- 历史回填：`--mode backfill --start <起> --end <止>`

## 主键

- `trade_date` / `build_id` / `target_id` / `result_type`

## 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| trade_date / build_id / build_name | string | 日期 / `B7` / `龙虎榜监控+席位标签库` |
| target_id / ts_code / name / board_type | string | 标的 |
| result_type | string | `lhb_stock`(个股) / `lhb_summary`(每日 1 行 MARKET 汇总) |
| result_value | string | `次日关注` / `上榜`；MARKET 行为 `N上榜/M关注` |
| is_watchlist / watchlist_rank / score / watch_reason | bool/int/float/string | 次日关注清单 |
| net_buy / inst_net / hotmoney_net / north_net / quant_net | float | 总/机构/游资/北向/量化 净买额 |
| known_seat_cnt / n_reasons / top_buy_seat | int/int/string | 知名席位数 / 上榜原因条数 / 最大买入席位 |
| type / reason / amount / change_rate / turnover | - | 上榜原因 / 金额 / 涨跌幅 / 换手 |
| result_json | string | 全状态 JSON（`buy_seats`/`sell_seats` 含 b/s 双金额 + `reasons` 按上榜原因拆分）；MARKET 行存汇总 dict |
| data_version / update_time | string | 版本 / 生成时间 |

> `result_json.reasons`：一票一天多条上榜原因，每条 `{type, reason, buy[], sell[], buy_total, sell_total}` —— 个股详情页用。
> 区间统计：`build.range_stats(panel, ts_code, start, end)` 从本 parquet 历史按营业部聚合总买/总卖/净额。

> **MARKET 行**：每个交易日额外一行 `target_id=MARKET` / `result_type=lhb_summary`，
> `result_json` 含 `n_lhb`/`n_inst_buy`/`n_hotmoney_buy`/`n_watchlist`/`inst_net_total`/`hotmoney_net_total`/`top_inst`/`seat_library`。

## 读取规则

```python
import pandas as pd, json
df = pd.read_parquet("build-b7-lhb-monitor/生产产物/database.parquet")
day = df[df["trade_date"] == df["trade_date"].max()]
stocks = day[day["result_type"] == "lhb_stock"]
summary = json.loads(day[day["result_type"] == "lhb_summary"].iloc[0]["result_json"])
stocks[stocks["is_watchlist"]].sort_values("watchlist_rank")          # 次日关注清单
stocks[stocks["inst_net"] > 0].sort_values("inst_net", ascending=False)  # 机构合集
# 某游资席位今天买了哪些：解析 result_json.buy_seats，按 tag 过滤
```

agent 按 `result_type` 先拆个股/汇总，再按 `trade_date`/`ts_code`/`is_watchlist`/`inst_net` 查询。
展示可调用开发产物 `render.render_markdown` / `render_html.render_html`。
回答需注明席位标签来自可维护种子库，应结合实际席位核对。

## 禁止行为

- 不允许多人查询时重复触发重抓取/重算（重算走开发产物 `maintain_daily`）。
- 不允许手工修改 Parquet 结果。
- 生产结果异常时必须提示数据日期和异常原因（如当日无龙虎榜、某接口降级）。
