#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUILD-B7 龙虎榜 —— 每日整理（Markdown 多维表格）
================================================================
  0. 概览（上榜家数 / 机构买入家数 / 游资活跃 / 次日关注数）
  1. 次日关注清单（按打分排序，带上榜理由）
  2. 机构合集（机构净买标的）
  3. 游资席位合集（知名游资席位 → 当日买入标的）
  4. 个股席位明细（关注清单前若干只的买/卖席位带标签）
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

STOCK_TYPE = "lhb_stock"
SUMMARY_TYPE = "lhb_summary"


def _split_day(panel: pd.DataFrame, date: str | None):
    if panel.empty:
        return panel, {}, ""
    panel = panel.copy()
    panel["trade_date"] = panel["trade_date"].astype(str)
    day = date or panel["trade_date"].max()
    day = pd.to_datetime(day).strftime("%Y-%m-%d")
    d = panel[panel["trade_date"] == day]
    stocks = d[d["result_type"] == STOCK_TYPE].copy()
    srow = d[d["result_type"] == SUMMARY_TYPE]
    summary = json.loads(srow.iloc[0]["result_json"]) if len(srow) else {}
    # 解析每只票的 result_json（席位明细）
    if not stocks.empty:
        stocks["_j"] = stocks["result_json"].apply(json.loads)
    return stocks, summary, day


def _yi(v) -> str:
    try:
        return f"{float(v)/1e8:.2f}亿"
    except Exception:
        return "—"


def _overview(d: pd.DataFrame, s: dict) -> str:
    n = int(s.get("n_lhb", len(d)))
    n_inst = int(s.get("n_inst_buy", int((d["inst_net"] > 0).sum())))
    n_hot = int(s.get("n_hotmoney_buy", int((d["hotmoney_net"] > 0).sum())))
    n_wl = int(s.get("n_watchlist", int(d["is_watchlist"].sum())))
    lib = s.get("seat_library", {})
    lib_txt = f"种子{lib.get('seed','?')}+覆盖{lib.get('override',0)}" if lib else "?"
    return (f"**上榜 {n} 家** ｜ 机构买入 {n_inst} ｜ 游资活跃 {n_hot} ｜ "
            f"**次日关注 {n_wl}** ｜ 机构合计净买 {_yi(s.get('inst_net_total',0))} ｜ "
            f"游资合计净买 {_yi(s.get('hotmoney_net_total',0))} ｜ 席位库 {lib_txt}")


def _watchlist_table(d: pd.DataFrame) -> str:
    wl = d[d["is_watchlist"]].sort_values("watchlist_rank")
    if wl.empty:
        return "_当日无入选次日关注清单的标的。_"
    lines = ["| # | 标的 | 板块 | 上榜理由 | 机构净买 | 游资净买 | 上榜原因 |",
             "|---:|---|---|---|---:|---:|---|"]
    for _, r in wl.iterrows():
        lines.append(
            f"| {int(r['watchlist_rank'])} | {r['name']}({r['ts_code']}) | {r['board_type']} | "
            f"{r['watch_reason']} | {_yi(r['inst_net'])} | {_yi(r['hotmoney_net'])} | {str(r.get('reason') or '')[:18]} |")
    return "\n".join(lines)


def _inst_table(d: pd.DataFrame) -> str:
    inst = d[d["inst_net"] > 0].sort_values("inst_net", ascending=False)
    if inst.empty:
        return "_当日无机构净买入标的。_"
    lines = ["| 标的 | 板块 | 机构净买 | 总净买 | 上榜原因 |", "|---|---|---:|---:|---|"]
    for _, r in inst.head(20).iterrows():
        lines.append(f"| {r['name']}({r['ts_code']}) | {r['board_type']} | {_yi(r['inst_net'])} | "
                     f"{_yi(r['net_buy'])} | {str(r.get('reason') or '')[:18]} |")
    return "\n".join(lines)


def _hotmoney_seat_table(d: pd.DataFrame) -> str:
    """知名游资席位 → 当日买入标的合集。"""
    seat_map: dict[str, list] = {}
    for _, r in d.iterrows():
        for seat in r["_j"].get("buy_seats", []):
            if seat.get("category") != "游资":
                continue
            tag = seat.get("tag") or seat.get("agency")
            seat_map.setdefault(tag, []).append((r["name"], r["ts_code"], seat.get("value", 0)))
    if not seat_map:
        return "_当日无标签库命中的知名游资席位。_"
    lines = ["| 游资席位 | 出手次数 | 买入标的（金额） |", "|---|---:|---|"]
    for tag, picks in sorted(seat_map.items(), key=lambda kv: -len(kv[1])):
        picks.sort(key=lambda x: -x[2])
        items = "，".join(f"{nm}({ts.split('.')[0]},{v/1e8:.2f}亿)" for nm, ts, v in picks[:8])
        lines.append(f"| **{tag}** | {len(picks)} | {items} |")
    return "\n".join(lines)


def _seat_detail(d: pd.DataFrame, top: int = 6) -> str:
    wl = d[d["is_watchlist"]].sort_values("watchlist_rank").head(top)
    if wl.empty:
        wl = d.sort_values("net_buy", ascending=False).head(top)
    blocks = []
    for _, r in wl.iterrows():
        j = r["_j"]
        def fmt(seats):
            return "，".join(f"{s.get('tag') or s.get('agency','')[:8]}[{s.get('category')}]{s['value']/1e8:.2f}亿"
                            for s in seats[:5]) or "—"
        blocks.append(f"**{r['name']}({r['ts_code']})** {r['board_type']}\n"
                      f"- 买：{fmt(j.get('buy_seats', []))}\n"
                      f"- 卖：{fmt(j.get('sell_seats', []))}")
    return "\n\n".join(blocks) if blocks else "_无_"


def _wan(v) -> str:
    try:
        return f"{float(v)/1e4:,.0f}"
    except Exception:
        return "—"


def _seat_tag_str(s: dict) -> str:
    cat, tag = s.get("category", ""), s.get("tag", "")
    if cat in ("机构", "北向"):
        return f"[{cat}]"
    if tag:
        return f"[{cat}·{tag}]"
    return f"[{cat}]" if cat and cat != "普通" else ""


def render_stock_detail(panel: pd.DataFrame, ts_code: str, date: str | None = None) -> str:
    """个股龙虎榜详情页（同花顺式）：按上榜原因拆分，每个原因列买入/卖出营业部表。"""
    df = panel[(panel.get("result_type") == STOCK_TYPE) & (panel["ts_code"].astype(str) == str(ts_code))].copy()
    if df.empty:
        return f"# {ts_code}\n\n_该票区间内无龙虎榜记录。_\n"
    df["trade_date"] = df["trade_date"].astype(str)
    day = pd.to_datetime(date).strftime("%Y-%m-%d") if date else df["trade_date"].max()
    row = df[df["trade_date"] == day]
    if row.empty:
        return f"# {ts_code} · {day}\n\n_该日无龙虎榜记录。_\n"
    r = row.iloc[0]
    j = json.loads(r["result_json"])
    head = (f"# 🐯 {r['name']}({r['ts_code']}) · {day}\n\n"
            f"> {r['board_type']} ｜ 净买入 **{_yi(j.get('net_buy',0))}** ｜ "
            f"机构净买 {_yi(j.get('inst_net',0))} ｜ 游资净买 {_yi(j.get('hotmoney_net',0))} ｜ "
            f"北向净买 {_yi(j.get('north_net',0))} ｜ 上榜原因 {j.get('n_reasons',1)} 条")
    blocks = [head]
    for rs in j.get("reasons", []):
        blocks.append(f"\n## 上榜原因：{rs.get('reason') or rs.get('type','')}")
        bt = ["| 买入营业部 | 标签 | 买入(万) | 卖出(万) |", "|---|---|---:|---:|"]
        for s in rs.get("buy", []):
            bt.append(f"| {s['agency']} | {_seat_tag_str(s)} | {_wan(s.get('b',0))} | {_wan(s.get('s',0))} |")
        bt.append(f"| **买入合计** | | **{_wan(rs.get('buy_total',0))}** | |")
        st = ["| 卖出营业部 | 标签 | 买入(万) | 卖出(万) |", "|---|---|---:|---:|"]
        for s in rs.get("sell", []):
            st.append(f"| {s['agency']} | {_seat_tag_str(s)} | {_wan(s.get('b',0))} | {_wan(s.get('s',0))} |")
        st.append(f"| **卖出合计** | | | **{_wan(rs.get('sell_total',0))}** |")
        blocks.append("\n".join(bt) + "\n\n" + "\n".join(st))
    return "\n".join(blocks) + "\n"


def render_range_stats(panel: pd.DataFrame, ts_code: str, start: str | None = None,
                       end: str | None = None) -> str:
    """区间统计：某票在区间内各营业部 总买/总卖/净额（按净额排序）。"""
    from build import range_stats
    rs = range_stats(panel, ts_code, start, end)
    if not rs.get("seats"):
        return f"# {ts_code} 区间统计\n\n_区间内无龙虎榜记录。_\n"
    lines = [f"# 📊 {rs.get('name','')}({rs['ts_code']}) 区间统计 · {rs['start']}~{rs['end']}（{rs['n_days']} 个上榜日）",
             "", "| 营业部 | 标签 | 总买(万) | 总卖(万) | 净额(万) | 上榜次数 |",
             "|---|---|---:|---:|---:|---:|"]
    for s in rs["seats"]:
        lines.append(f"| {s['agency']} | {_seat_tag_str(s)} | {_wan(s['buy'])} | {_wan(s['sell'])} | "
                     f"{_wan(s['net'])} | {s['days']} |")
    return "\n".join(lines) + "\n"


def render_markdown(panel: pd.DataFrame, date: str | None = None) -> str:
    d, s, day = _split_day(panel, date)
    if d.empty:
        return f"# 龙虎榜监控 {day or ''}\n\n_当日无龙虎榜数据。_\n"
    parts = [
        f"# 🐯 龙虎榜监控 · 席位标签库 · {day}",
        "", f"> {_overview(d, s)}", "",
        "## 一、次日关注清单", "", _watchlist_table(d), "",
        "## 二、机构合集（机构净买）", "", _inst_table(d), "",
        "## 三、游资席位合集", "", _hotmoney_seat_table(d), "",
        "## 四、个股席位明细（关注清单 Top）", "", _seat_detail(d), "",
        "---", "_BUILD-B7 龙虎榜监控+席位标签库 · 席位标签为可维护种子库，请持续核对_",
    ]
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description="B7 龙虎榜 Markdown 整理")
    ap.add_argument("--parquet", default=str(Path(__file__).resolve().parents[2] / "生产产物" / "database.parquet"))
    ap.add_argument("--date", default=None)
    ap.add_argument("--stock", default=None, help="出某票个股龙虎榜详情页（按上榜原因拆买卖营业部）")
    ap.add_argument("--range", action="store_true", help="配合 --stock：出区间统计而非单日详情")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    panel = pd.read_parquet(args.parquet)
    if args.stock and getattr(args, "range"):
        md = render_range_stats(panel, args.stock, args.start, args.end)
    elif args.stock:
        md = render_stock_detail(panel, args.stock, date=args.date)
    else:
        md = render_markdown(panel, date=args.date)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"已写出 {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
