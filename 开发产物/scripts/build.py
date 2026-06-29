#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUILD-B7: 龙虎榜监控 + 席位标签库
================================================================
工具定位（BUILD开发与生产规则V2.md §3）：监控预警型 BUILD。

核心能力：
  1. 收盘后自动抓取龙虎榜：get_lhb_list（异动股）+ get_lhb_detail（买/卖席位明细，全市场）。
  2. 匹配席位标签：seat_tags.match_seat 把每个营业部映射为 北向/机构/游资/量化/普通 + 席位俗称。
  3. 每日整理：机构合集（机构净买标的）、营业部合集（知名游资席位→其当日标的）、个股席位明细。
  4. 生成次日关注清单：按 机构净买 / 知名游资净买 / 买卖力量 / 上榜原因 综合打分排序。
  5. 可视化：render_html 暗色看板 + render markdown 多维整理。

数据源：PandaData（panda_data ≥ 0.0.9）。凭证用环境变量 PANDA_USERNAME / PANDA_PASSWORD
（兼容 PANDA_DATA_*）。龙虎榜是事件型，仅异动日有数据；当日无上榜 → 返回空表。

参考：skills_dev/.../capital_pricing/seat_analysis（旧数据，仅借鉴四类席位分类逻辑；
数据一律以 PandaData 实际返回为准）。
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

import seat_tags

BUILD_ID = "B7"
BUILD_NAME = "龙虎榜监控+席位标签库"
RESULT_STOCK = "lhb_stock"
RESULT_SUMMARY = "lhb_summary"
DEFAULT_DATA_VERSION = "pandadata-lhb-monitor-v1"

DEV_ROOT = Path(__file__).resolve().parents[1]            # 开发产物
BUILD_ROOT = DEV_ROOT.parent                              # build-b7-lhb-monitor
DEFAULT_OUT = BUILD_ROOT / "生产产物" / "database.parquet"

# 次日关注清单默认打分权重
DEFAULT_CONFIG: dict = {
    "weights": {"inst_net": 0.35, "hotmoney_net": 0.35, "net_buy": 0.20, "known_seat_cnt": 0.10},
    "watchlist_top_n": 20,
    "min_score": 0.0,   # 入选次日清单的最低分（z 综合）
}


# ============================================================
# 工具
# ============================================================
def _compact(s: Any) -> str:
    return str(s).strip().replace("-", "").replace("/", "")[:8]


def _norm_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s.astype(str).str.replace(r"\.0$", "", regex=True), errors="coerce")


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def _is_quota_or_service_error(exc: Exception) -> bool:
    t = str(exc)
    return any(k in t for k in ("500009", "单日总流量超限", "200103", "权限不足",
                                 "ServiceError", "空 detail", "504", "Gateway Time-out"))


def _zscore(x: pd.Series) -> pd.Series:
    sd = x.std(ddof=0)
    if not sd or np.isnan(sd):
        return pd.Series(0.0, index=x.index)
    return ((x - x.mean()) / sd).clip(-5, 5)


def board_type_of(ts_code: str) -> str:
    c = str(ts_code).upper()
    if c.endswith(".BJ"):
        return "北交所"
    if c.startswith(("688", "689")) and c.endswith(".SH"):
        return "科创板"
    if c.startswith(("300", "301")) and c.endswith(".SZ"):
        return "创业板"
    if c.startswith(("600", "601", "603", "605")) and c.endswith(".SH"):
        return "沪主板"
    if c.startswith(("000", "001", "002", "003")) and c.endswith(".SZ"):
        return "深主板"
    return "其他"


# ============================================================
# 数据层
# ============================================================
def init_panda() -> Any:
    try:
        import panda_data
    except ModuleNotFoundError as exc:
        raise RuntimeError("无法导入 panda_data，请先 `pip install --upgrade panda_data`（需 ≥0.0.9）") from exc
    user = os.getenv("PANDA_USERNAME") or os.getenv("PANDA_DATA_USERNAME")
    pwd = os.getenv("PANDA_PASSWORD") or os.getenv("PANDA_DATA_PASSWORD")
    if not (user and pwd):
        raise RuntimeError("缺少 PANDA_USERNAME / PANDA_PASSWORD 环境变量")
    base_url = os.getenv("PANDA_BASE_URL")
    if base_url:
        panda_data.init_token(username=user, password=pwd, base_url=base_url)
    else:
        panda_data.init_token(username=user, password=pwd)
    return panda_data


def resolve_last_trade(end_date: str, pd_api: Any) -> str:
    """返回 <= end_date 的最近交易日。优先用交易日历，回退 get_last_trade_date()。"""
    end_c = _compact(end_date)
    try:
        start = _compact((pd.to_datetime(end_c) - timedelta(days=15)).strftime("%Y%m%d"))
        cal = pd_api.get_trade_cal(start_date=start, end_date=end_c, is_trading_day=1)
        if cal is not None and not cal.empty:
            col = "date" if "date" in cal.columns else cal.columns[0]
            days = sorted(_compact(x) for x in cal[col].tolist())
            days = [d for d in days if d <= end_c]
            if days:
                return days[-1]
    except Exception:
        pass
    try:
        last = pd_api.get_last_trade_date()
        if isinstance(last, pd.DataFrame) and not last.empty:
            last = str(last.iloc[0, 0])
        return _compact(last) if last else end_c
    except Exception:
        return end_c


def _norm_detail(df: pd.DataFrame, side: str) -> pd.DataFrame:
    cols = ["ts_code", "trade_date", "side", "type", "rank", "agency", "b_value", "s_value", "reason"]
    if df is None or df.empty:
        # 显式 dtype 的空表：避免单边日(仅买或仅卖) concat 时把 b_value/s_value 污染成 object，
        # 进而令下游 "b_value - s_value" 抛 TypeError（float64 vs object）。
        empty = pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
        for c in ("b_value", "s_value", "rank"):
            empty[c] = pd.Series(dtype="float64")
        empty["trade_date"] = pd.Series(dtype="datetime64[ns]")
        return empty
    df = df.rename(columns={"symbol": "ts_code", "date": "trade_date"}).copy()
    for c in ["agency", "reason", "type"]:
        if c not in df.columns:
            df[c] = ""
    for c in ["b_value", "s_value"]:
        df[c] = _num(df[c]) if c in df.columns else 0.0
    df["rank"] = pd.to_numeric(df.get("rank"), errors="coerce")
    df["trade_date"] = _norm_date(df["trade_date"])
    df["side"] = df.get("side", side).fillna(side) if "side" in df.columns else side
    df["agency"] = df["agency"].fillna("").astype(str)
    df["type"] = df["type"].fillna("").astype(str)
    df["reason"] = df["reason"].fillna("").astype(str)
    return df[cols]


def _norm_list(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["ts_code", "trade_date", "type", "reason", "amount", "change_rate", "turnover"])
    df = df.rename(columns={"symbol": "ts_code", "date": "trade_date"}).copy()
    for c in ["type", "reason"]:
        if c not in df.columns:
            df[c] = ""
    for c in ["amount", "change_rate", "turnover", "deviation"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        else:
            df[c] = np.nan
    df["trade_date"] = _norm_date(df["trade_date"])
    # 一只票一天可能多条上榜原因 → 合并 reason，取 amount 最大
    agg = (df.sort_values("amount", ascending=False)
           .groupby(["ts_code", "trade_date"], as_index=False)
           .agg(type=("type", lambda s: ",".join(sorted(set(s.dropna().astype(str))))),
                reason=("reason", lambda s: ";".join(sorted(set(s.dropna().astype(str))))),
                amount=("amount", "max"), change_rate=("change_rate", "first"),
                turnover=("turnover", "first")))
    return agg


def fetch_lhb(date: str, pd_api: Any | None = None) -> dict:
    """抓取单日龙虎榜：异动股列表 + 买/卖席位明细。返回 dict(list, buy, sell)。"""
    pd_api = pd_api or init_panda()
    d = _compact(date)
    lst = buy = sell = None
    try:
        lst = pd_api.get_lhb_list(symbol="", type=None, start_date=d, end_date=d, fields=[])
    except Exception as exc:  # noqa: BLE001
        if _is_quota_or_service_error(exc):
            raise
        print(f"  [warn] get_lhb_list 失败: {str(exc)[:80]}")
    try:
        buy = pd_api.get_lhb_detail(symbol=None, type=None, start_date=d, end_date=d, side="buy", fields=[])
    except Exception as exc:  # noqa: BLE001
        if _is_quota_or_service_error(exc):
            raise
        print(f"  [warn] get_lhb_detail(buy) 失败: {str(exc)[:80]}")
    try:
        sell = pd_api.get_lhb_detail(symbol=None, type=None, start_date=d, end_date=d, side="sell", fields=[])
    except Exception as exc:  # noqa: BLE001
        if _is_quota_or_service_error(exc):
            raise
        print(f"  [warn] get_lhb_detail(sell) 失败: {str(exc)[:80]}")
    return {"list": _norm_list(lst), "buy": _norm_detail(buy, "buy"), "sell": _norm_detail(sell, "sell")}


def load_names(symbols: list[str], pd_api: Any | None = None) -> dict:
    """股票名映射（失败返回空，名称留空不影响主流程）。"""
    if not symbols:
        return {}
    try:
        pd_api = pd_api or init_panda()
        d = pd_api.get_stock_detail(symbol=list(symbols), market="cn", fields=["name"])
        if d is not None and not d.empty:
            d = d.rename(columns={"symbol": "ts_code"})
            return dict(zip(d["ts_code"].astype(str), d["name"].astype(str)))
    except Exception as exc:  # noqa: BLE001
        print(f"  [warn] 股票名拉取失败，name 留空: {str(exc)[:60]}")
    return {}


# ============================================================
# 席位聚合 + 个股汇总
# ============================================================
def _tag_seats(detail: pd.DataFrame) -> pd.DataFrame:
    if detail.empty:
        return detail.assign(category="", tag="", note="", group="", tier="", alias="")
    tags = detail["agency"].map(seat_tags.match_seat)
    detail = detail.copy()
    for k in ["category", "tag", "note", "group", "tier", "alias"]:
        detail[k] = [t.get(k, "") for t in tags]
    return detail


def _seats_from(rows: pd.DataFrame, sort_col: str) -> list:
    """把席位行转 dict 列表，每个席位带 买入(b) / 卖出(s) 两个金额 + 标签 + 帮派。
    value = 该侧主金额（买方表用 b，卖方表用 s），兼容旧渲染。"""
    out = []
    for _, r in rows.sort_values(sort_col, ascending=False).iterrows():
        b, s = float(r["b_value"]), float(r["s_value"])
        if b <= 0 and s <= 0:
            continue
        seat = {"agency": r["agency"], "category": r["category"], "tag": r["tag"],
                "b": round(b, 0), "s": round(s, 0),
                "value": round(b if sort_col == "b_value" else s, 0),
                "rank": (int(r["rank"]) if pd.notna(r["rank"]) else None)}
        for k in ["group", "tier", "alias"]:
            if r.get(k):
                seat[k] = r[k]
        out.append(seat)
    return out


def _agg_seats(side_rows: pd.DataFrame, val: str) -> list:
    """同一席位跨多个上榜原因合并（用于个股汇总的买/卖席位列表与合集视图）。"""
    if side_rows.empty:
        return []
    for c in ["group", "tier", "alias"]:
        if c not in side_rows.columns:
            side_rows = side_rows.assign(**{c: ""})
    a = side_rows.groupby(["agency", "category", "tag", "group", "tier", "alias"], as_index=False).agg(
        b_value=("b_value", "sum"), s_value=("s_value", "sum"), rank=("rank", "min"))
    return _seats_from(a, val)


def _reasons_breakdown(g: pd.DataFrame, fallback_type: str = "", fallback_reason: str = "") -> list:
    """按上榜原因(type)拆分：每个原因 → 买入营业部组 + 卖出营业部组（含各自总计）。
    对应同花顺式个股龙虎榜详情页（一只票一天可有多条上榜原因）。
    detail 无 type（仅 list 侧给出上榜原因代码）时，回退用 list 级 type/reason 标注，
    避免原因分组退化成空键 type=""（list/detail 口径不一致问题）。"""
    reasons = []
    for typ, gt in g.groupby("type", sort=False):
        typ = str(typ)
        gtb, gts = gt[gt["side"] == "buy"], gt[gt["side"] == "sell"]
        reasons.append({
            "type": typ or fallback_type,
            "reason": "；".join(sorted(set(gt["reason"]) - {""})) or fallback_reason,
            "buy": _seats_from(gtb, "b_value"),
            "sell": _seats_from(gts, "s_value"),
            "buy_total": round(float(gtb["b_value"].sum()), 0),
            "sell_total": round(float(gts["s_value"].sum()), 0),
        })
    # 原因按买入总额降序（主力上榜原因在前）
    return sorted(reasons, key=lambda x: -x["buy_total"])


def build_pool(fetched: dict, names: Optional[dict] = None) -> pd.DataFrame:
    """把单日龙虎榜聚合成个股级面板（每股一行 + 席位明细 + 分类净额）。"""
    names = names or {}
    buy = _tag_seats(fetched["buy"])
    sell = _tag_seats(fetched["sell"])
    lst = fetched["list"]
    if buy.empty and sell.empty and lst.empty:
        return pd.DataFrame()

    # 单边日(仅买方或仅卖方)防御：先过滤空表再 concat（避免空表 dtype 污染 + FutureWarning），
    # 再强制数值化 b_value/s_value，杜绝下方 "b_value - s_value" 因 object dtype 崩溃。
    detail_parts = [d for d in (buy, sell) if not d.empty]
    detail = pd.concat(detail_parts, ignore_index=True) if detail_parts else buy.iloc[0:0].copy()
    detail["b_value"] = _num(detail["b_value"])
    detail["s_value"] = _num(detail["s_value"])
    keys = detail[["ts_code", "trade_date"]].drop_duplicates()
    if lst is not None and not lst.empty:
        keys = pd.concat([keys, lst[["ts_code", "trade_date"]]], ignore_index=True).drop_duplicates()

    # list 级上榜原因（type/reason）查找表，detail 无 type 时作回退标注
    lst_reason: dict = {}
    if lst is not None and not lst.empty:
        for _, lr in lst.iterrows():
            lst_reason[(str(lr["ts_code"]), pd.Timestamp(lr["trade_date"]))] = (
                str(lr.get("type", "") or ""), str(lr.get("reason", "") or ""))

    rows = []
    grp_detail = detail.groupby(["ts_code", "trade_date"], sort=False)
    for (ts, td), g in grp_detail:
        gb = g[g["side"] == "buy"]
        gs = g[g["side"] == "sell"]
        total_buy = float(gb["b_value"].sum())
        total_sell = float(gs["s_value"].sum())
        inst_net = float(g[g["category"] == "机构"].eval("b_value - s_value").sum())
        # 游资盘净买 = 知名游资 + 其他具名营业部（非机构/非北向/非量化的活跃资金）
        hot_net = float(g[g["category"].isin(seat_tags.HOTMONEY_CATS)].eval("b_value - s_value").sum())
        north_net = float(g[g["category"] == "北向"].eval("b_value - s_value").sum())
        quant_net = float(g[g["category"] == "量化"].eval("b_value - s_value").sum())
        famous = g[g["category"] == "游资"]                       # 种子库命中的知名游资
        known_buy_seats = sorted(set(gb[gb["category"] == "游资"]["tag"]) - {""})
        top_buy = gb.sort_values("b_value", ascending=False).head(1)
        top_buy_seat = (top_buy.iloc[0]["tag"] or top_buy.iloc[0]["agency"]) if len(top_buy) else ""
        rows.append({
            "ts_code": ts, "trade_date": td,
            "total_buy": total_buy, "total_sell": total_sell, "net_buy": total_buy - total_sell,
            "inst_net": inst_net, "hotmoney_net": hot_net, "north_net": north_net, "quant_net": quant_net,
            "known_seat_cnt": int(famous["agency"].nunique()),   # 知名游资席位数（高亮用）
            "desk_seat_cnt": int(g[g["category"].isin(seat_tags.HOTMONEY_CATS)]["agency"].nunique()),
            "hotmoney_seats": known_buy_seats, "top_buy_seat": top_buy_seat,
            "n_reasons": int(g["type"].nunique()),
            "buy_seats": _agg_seats(gb, "b_value"), "sell_seats": _agg_seats(gs, "s_value"),
            "reasons": _reasons_breakdown(g, *lst_reason.get((str(ts), pd.Timestamp(td)), ("", ""))),
        })
    pool = pd.DataFrame(rows)
    if pool.empty:
        pool = keys.copy()
        for c in ["total_buy", "total_sell", "net_buy", "inst_net", "hotmoney_net", "north_net",
                  "quant_net", "known_seat_cnt", "desk_seat_cnt"]:
            pool[c] = 0.0
        pool["hotmoney_seats"] = [[] for _ in range(len(pool))]
        pool["buy_seats"] = [[] for _ in range(len(pool))]
        pool["sell_seats"] = [[] for _ in range(len(pool))]
        pool["reasons"] = [[] for _ in range(len(pool))]
        pool["n_reasons"] = 0
        pool["top_buy_seat"] = ""

    # 合入异动信息
    if lst is not None and not lst.empty:
        pool = pool.merge(lst, on=["ts_code", "trade_date"], how="outer")
    for c in ["type", "reason"]:
        if c not in pool.columns:
            pool[c] = ""
        pool[c] = pool[c].fillna("")
    for c in ["amount", "change_rate", "turnover"]:
        if c not in pool.columns:
            pool[c] = np.nan
    # outer merge 可能带来 NaN 数值列
    for c in ["total_buy", "total_sell", "net_buy", "inst_net", "hotmoney_net", "north_net", "quant_net", "known_seat_cnt", "desk_seat_cnt", "n_reasons"]:
        pool[c] = _num(pool.get(c))
    for c in ["hotmoney_seats", "buy_seats", "sell_seats", "reasons"]:
        pool[c] = pool[c].apply(lambda v: v if isinstance(v, list) else [])
    pool["top_buy_seat"] = pool.get("top_buy_seat", "").fillna("")
    pool["board_type"] = pool["ts_code"].map(board_type_of)
    pool["name"] = pool["ts_code"].map(lambda c: names.get(c, ""))
    return pool.reset_index(drop=True)


# ============================================================
# 次日关注清单打分
# ============================================================
def compute_watchlist(pool: pd.DataFrame, cfg: dict = DEFAULT_CONFIG) -> pd.DataFrame:
    if pool.empty:
        return pool
    df = pool.copy()
    w = cfg["weights"]
    df["score"] = (
        w["inst_net"] * _zscore(df["inst_net"])
        + w["hotmoney_net"] * _zscore(df["hotmoney_net"])
        + w["net_buy"] * _zscore(df["net_buy"])
        + w["known_seat_cnt"] * _zscore(df["known_seat_cnt"].astype(float))
    ).round(4)
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["watchlist_rank"] = np.arange(1, len(df) + 1)
    top_n = cfg.get("watchlist_top_n", 20)
    df["is_watchlist"] = (df["watchlist_rank"] <= top_n) & (df["score"] >= cfg.get("min_score", 0.0)) \
        & ((df["inst_net"] > 0) | (df["hotmoney_net"] > 0) | (df["net_buy"] > 0))

    def _reason(r) -> str:
        bits = []
        if r["inst_net"] > 0:
            bits.append(f"机构净买{r['inst_net']/1e8:.2f}亿")
        if r["hotmoney_net"] > 0:
            seats = "/".join(r["hotmoney_seats"][:3]) if r["hotmoney_seats"] else "游资"
            bits.append(f"游资净买{r['hotmoney_net']/1e8:.2f}亿({seats})")
        if r["north_net"] > 0:
            bits.append(f"北向净买{r['north_net']/1e8:.2f}亿")
        if not bits and r["net_buy"] > 0:
            bits.append(f"榜单净买{r['net_buy']/1e8:.2f}亿")
        if r.get("reason"):
            bits.append(str(r["reason"]).split(";")[0])
        return " ｜ ".join(bits) if bits else "净卖出/分歧"
    df["watch_reason"] = df.apply(_reason, axis=1)
    return df


# ============================================================
# 标准化输出
# ============================================================
OUTPUT_COLS = [
    "trade_date", "build_id", "build_name", "target_id", "result_type",
    "ts_code", "name", "board_type",
    "is_watchlist", "watchlist_rank", "score", "watch_reason",
    "net_buy", "inst_net", "hotmoney_net", "north_net", "quant_net",
    "known_seat_cnt", "desk_seat_cnt", "n_reasons", "top_buy_seat", "type", "reason", "amount", "change_rate", "turnover",
    "result_value", "result_json", "data_version", "update_time",
]


def range_stats(panel: pd.DataFrame, ts_code: str, start: str | None = None,
                end: str | None = None) -> dict:
    """区间统计：对某只票在 [start,end] 内，按营业部汇总 总买/总卖/净额/上榜次数。
    从已落地的 parquet 历史读取（每日 result_json 的 buy_seats/sell_seats 含 b/s）。
    返回 {ts_code, name, start, end, n_days, range_change, seats:[...排序后]}。"""
    df = panel[(panel["result_type"] == RESULT_STOCK) & (panel["ts_code"].astype(str) == str(ts_code))].copy()
    if df.empty:
        return {"ts_code": ts_code, "seats": [], "n_days": 0}
    df["trade_date"] = df["trade_date"].astype(str)
    if start:
        df = df[df["trade_date"] >= pd.to_datetime(_compact(start)).strftime("%Y-%m-%d")]
    if end:
        df = df[df["trade_date"] <= pd.to_datetime(_compact(end)).strftime("%Y-%m-%d")]
    if df.empty:
        return {"ts_code": ts_code, "seats": [], "n_days": 0}
    name = df["name"].dropna().astype(str).iloc[0] if df["name"].notna().any() else ""
    agg: dict[str, dict] = {}
    for _, r in df.iterrows():
        j = json.loads(r["result_json"])
        for seat in (j.get("buy_seats", []) + j.get("sell_seats", [])):
            key = seat["agency"]
            a = agg.setdefault(key, {"agency": key, "category": seat.get("category", "普通"),
                                     "tag": seat.get("tag", ""), "buy": 0.0, "sell": 0.0, "_dates": set()})
            a["buy"] += float(seat.get("b", seat.get("value", 0)) or 0)
            a["sell"] += float(seat.get("s", 0) or 0)
            a["_dates"].add(r["trade_date"])   # 上榜天数按 trade_date 去重（同日既买又卖只算 1 天）
    seats = sorted(agg.values(), key=lambda x: -(x["buy"] - x["sell"]))
    for s in seats:
        s["days"] = len(s.pop("_dates"))
        s["net"] = round(s["buy"] - s["sell"], 0)
        s["buy"], s["sell"] = round(s["buy"], 0), round(s["sell"], 0)
    return {"ts_code": str(ts_code), "name": name,
            "start": df["trade_date"].min(), "end": df["trade_date"].max(),
            "n_days": int(df["trade_date"].nunique()), "seats": seats}


def to_standard_output(pool: pd.DataFrame, data_version: str = DEFAULT_DATA_VERSION) -> pd.DataFrame:
    if pool.empty:
        return pd.DataFrame(columns=OUTPUT_COLS)
    df = pool.copy()
    if "score" not in df.columns:
        df = compute_watchlist(df)
    td = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
    df["trade_date"] = td
    df["build_id"] = BUILD_ID
    df["build_name"] = BUILD_NAME
    df["result_type"] = RESULT_STOCK
    df["target_id"] = df["ts_code"].astype(str)
    df["is_watchlist"] = df["is_watchlist"].fillna(False).astype(bool)
    df["watchlist_rank"] = df["watchlist_rank"].fillna(0).astype(int)
    df["known_seat_cnt"] = df["known_seat_cnt"].fillna(0).astype(int)
    df["desk_seat_cnt"] = df.get("desk_seat_cnt", 0)
    df["desk_seat_cnt"] = df["desk_seat_cnt"].fillna(0).astype(int)
    df["result_value"] = np.where(df["is_watchlist"], "次日关注", "上榜")

    def _row_json(r) -> str:
        return json.dumps({
            "net_buy": round(float(r["net_buy"]), 0),
            "inst_net": round(float(r["inst_net"]), 0),
            "hotmoney_net": round(float(r["hotmoney_net"]), 0),
            "north_net": round(float(r["north_net"]), 0),
            "quant_net": round(float(r["quant_net"]), 0),
            "known_seat_cnt": int(r["known_seat_cnt"]),
            "desk_seat_cnt": int(r.get("desk_seat_cnt", 0) or 0),
            "top_buy_seat": r.get("top_buy_seat", ""),
            "hotmoney_seats": r.get("hotmoney_seats", []),
            "buy_seats": r.get("buy_seats", []),
            "sell_seats": r.get("sell_seats", []),
            "n_reasons": int(r.get("n_reasons", 0) or 0),
            "reasons": r.get("reasons", []),
            "is_watchlist": bool(r["is_watchlist"]),
            "watchlist_rank": int(r["watchlist_rank"]),
            "score": round(float(r["score"]), 4) if pd.notna(r.get("score")) else None,
            "watch_reason": r.get("watch_reason", ""),
            "type": r.get("type", ""), "reason": r.get("reason", ""),
            "amount": round(float(r["amount"]), 0) if pd.notna(r.get("amount")) else None,
            "change_rate": round(float(r["change_rate"]), 4) if pd.notna(r.get("change_rate")) else None,
        }, ensure_ascii=False)
    df["result_json"] = df.apply(_row_json, axis=1)
    df["data_version"] = data_version
    now_iso = datetime.now().isoformat(timespec="seconds")
    df["update_time"] = now_iso
    for c in OUTPUT_COLS:
        if c not in df.columns:
            df[c] = None
    out = df[OUTPUT_COLS].sort_values("watchlist_rank").reset_index(drop=True)

    # 市场汇总行
    summary = {
        "n_lhb": int(len(out)),
        "n_inst_buy": int((out["inst_net"] > 0).sum()),
        "n_hotmoney_buy": int((out["hotmoney_net"] > 0).sum()),
        "n_watchlist": int(out["is_watchlist"].sum()),
        "inst_net_total": round(float(out["inst_net"].sum()), 0),
        "hotmoney_net_total": round(float(out["hotmoney_net"].sum()), 0),
        "top_inst": out.sort_values("inst_net", ascending=False).head(5)["ts_code"].tolist(),
        "seat_library": seat_tags.library_size(),
    }
    mrow = {c: None for c in OUTPUT_COLS}
    mrow.update({
        "trade_date": td.iloc[0], "build_id": BUILD_ID, "build_name": BUILD_NAME,
        "target_id": "MARKET", "result_type": RESULT_SUMMARY, "ts_code": "MARKET", "name": "龙虎榜汇总",
        "is_watchlist": False, "watchlist_rank": 0, "known_seat_cnt": 0,
        "result_value": f"{summary['n_lhb']}上榜/{summary['n_watchlist']}关注",
        "result_json": json.dumps(summary, ensure_ascii=False),
        "data_version": data_version, "update_time": now_iso,
    })
    mdf = pd.DataFrame([mrow]).reindex(columns=out.columns).astype(out.dtypes.to_dict(), errors="ignore")
    return pd.concat([out, mdf], ignore_index=True)


def check_quality(panel: pd.DataFrame) -> list[str]:
    errs = []
    if panel.empty:
        return ["龙虎榜为空（当日可能无上榜，或数据未返回）"]
    dup = panel.duplicated(subset=["trade_date", "build_id", "target_id", "result_type"], keep=False)
    if dup.any():
        errs.append(f"主键重复 {int(dup.sum())} 条")
    for c in ["trade_date", "build_id", "target_id", "result_type", "result_value"]:
        if panel[c].isnull().any():
            errs.append(f"必填字段 '{c}' 存在空值")
    bad = panel[~panel["result_json"].apply(_is_json)]
    if len(bad):
        errs.append(f"result_json 不可解析 {len(bad)} 条")
    return errs


def _is_json(s: Any) -> bool:
    try:
        json.loads(s)
        return True
    except Exception:
        return False


# ============================================================
# 标准入口
# ============================================================
def validate_input(input_data: Any) -> dict:
    """校验调用方传入的龙虎榜结构化数据。
    接受 dict{list, buy, sell}（各为 records / DataFrame），或单个明细 records 列表（视为 buy+sell 混合）。"""
    if input_data is None:
        raise ValueError("input_data 不能为空")
    if isinstance(input_data, dict):
        out = {}
        for k in ["list", "buy", "sell"]:
            v = input_data.get(k)
            out[k] = pd.DataFrame(v) if v is not None else pd.DataFrame()
        if out["buy"].empty and out["sell"].empty and out["list"].empty:
            raise ValueError("input_data 的 list/buy/sell 不能全为空")
        return {"list": _norm_list(out["list"]), "buy": _norm_detail(out["buy"], "buy"),
                "sell": _norm_detail(out["sell"], "sell")}
    df = pd.DataFrame(input_data)
    if df.empty:
        raise ValueError("input_data 不能为空表")
    need = {"ts_code", "agency"} if "ts_code" in df.columns else {"symbol", "agency"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"input_data 缺少必要字段: {sorted(missing)}")
    side = df.get("side", "buy")
    buy = df[df["side"] == "buy"] if "side" in df.columns else df
    sell = df[df["side"] == "sell"] if "side" in df.columns else pd.DataFrame()
    return {"list": pd.DataFrame(columns=["ts_code", "trade_date"]),
            "buy": _norm_detail(buy, "buy"), "sell": _norm_detail(sell, "sell")}


def run(input_data: Any, config: dict | None = None) -> pd.DataFrame:
    """标准调用入口（BUILD 规则 §6）。

    Args:
        input_data: dict{list, buy, sell}（fetch_lhb 的输出形态），或席位明细 records。
        config: {"names": {ts_code:name}, "data_version": str, 以及打分权重覆盖}
    Returns:
        标准化龙虎榜面板（OUTPUT_COLS）+ 1 行市场汇总。
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    fetched = validate_input(input_data)
    pool = build_pool(fetched, names=cfg.get("names"))
    if pool.empty:
        return pd.DataFrame(columns=OUTPUT_COLS)
    pool = compute_watchlist(pool, cfg)
    return to_standard_output(pool, data_version=str(cfg.get("data_version", DEFAULT_DATA_VERSION)))


def maintain_daily(end_date: str | None = None, pd_api: Any | None = None,
                   cfg: dict = DEFAULT_CONFIG) -> pd.DataFrame:
    """每日维护：抓取 + 席位标签 + 次日清单（生产任务调用）。"""
    pd_api = pd_api or init_panda()
    end_date = end_date or datetime.now().strftime("%Y%m%d")
    last = resolve_last_trade(end_date, pd_api)
    print(f"[1/4] 抓取龙虎榜（{last}）...")
    fetched = fetch_lhb(last, pd_api)
    n = len(fetched["list"]) if not fetched["list"].empty else fetched["buy"]["ts_code"].nunique()
    print(f"      上榜标的 ~{n} 只，买方席位 {len(fetched['buy'])} 条 / 卖方 {len(fetched['sell'])} 条")
    if fetched["buy"].empty and fetched["sell"].empty and fetched["list"].empty:
        print("      当日无龙虎榜数据。")
        return pd.DataFrame(columns=OUTPUT_COLS)

    print("[2/4] 拉取股票名 ...")
    syms = pd.concat([fetched["buy"]["ts_code"], fetched["sell"]["ts_code"], fetched["list"]["ts_code"]]).dropna().unique().tolist()
    names = load_names(syms, pd_api)

    print("[3/4] 席位标签匹配 + 个股聚合 ...")
    pool = build_pool(fetched, names=names)

    print("[4/4] 次日关注清单打分 + 标准化 ...")
    pool = compute_watchlist(pool, cfg)
    out = to_standard_output(pool)
    errs = check_quality(out)
    print("  [PASS] 质量检查通过" if not errs else "  [FAIL] " + "; ".join(errs))
    return out


def backfill(start_date: str, end_date: str, pd_api: Any | None = None,
             cfg: dict = DEFAULT_CONFIG) -> pd.DataFrame:
    """区间回填：龙虎榜按日抓取（事件型，逐日 cheap）。"""
    pd_api = pd_api or init_panda()
    try:
        cal = pd_api.get_trade_cal(start_date=_compact(start_date), end_date=_compact(end_date), exchange="SH")
        days = [_compact(x) for x in (cal["date"] if "date" in cal.columns else cal.iloc[:, 0]).tolist()]
    except Exception:
        days = [(pd.to_datetime(_compact(start_date)) + timedelta(days=i)).strftime("%Y%m%d")
                for i in range((pd.to_datetime(_compact(end_date)) - pd.to_datetime(_compact(start_date))).days + 1)]
    frames = []
    for d in days:
        try:
            fetched = fetch_lhb(d, pd_api)
        except Exception as exc:  # noqa: BLE001
            if _is_quota_or_service_error(exc):
                print(f"  [warn] {d} 配额/服务异常，中断回填: {str(exc)[:50]}")
                break
            continue
        if fetched["buy"].empty and fetched["sell"].empty and fetched["list"].empty:
            continue
        syms = pd.concat([fetched["buy"]["ts_code"], fetched["sell"]["ts_code"]]).dropna().unique().tolist()
        names = load_names(syms, pd_api)
        pool = compute_watchlist(build_pool(fetched, names=names), cfg)
        frames.append(to_standard_output(pool))
    if not frames:
        return pd.DataFrame(columns=OUTPUT_COLS)
    return pd.concat(frames, ignore_index=True)


def save_parquet(panel: pd.DataFrame, out_path: str | Path = DEFAULT_OUT, append: bool = True) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if append and out_path.exists():
        try:
            old = pd.read_parquet(out_path)
            panel = pd.concat([old, panel], ignore_index=True).drop_duplicates(
                subset=["trade_date", "build_id", "target_id", "result_type"], keep="last")
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] 读取旧 parquet 失败，改为覆盖写: {exc}")
    panel = panel.sort_values(["trade_date", "watchlist_rank"])
    panel.to_parquet(out_path, index=False)
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser(description="BUILD-B7 龙虎榜监控+席位标签库")
    ap.add_argument("--mode", choices=["daily", "backfill"], default="daily")
    ap.add_argument("--date", default=datetime.now().strftime("%Y%m%d"))
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--no-append", action="store_true")
    args = ap.parse_args()

    print("=" * 64)
    print(f"BUILD-B7 龙虎榜监控+席位标签库 | mode={args.mode}")
    print("=" * 64)
    if args.mode == "daily":
        panel = maintain_daily(args.date)
    else:
        if not (args.start and args.end):
            raise SystemExit("backfill 模式需 --start 和 --end")
        panel = backfill(args.start, args.end)

    if panel.empty:
        print("龙虎榜为空，退出。")
        return
    path = save_parquet(panel, args.out, append=not args.no_append)
    print(f"\n已保存 {len(panel)} 条 → {path}")
    latest = panel[panel["trade_date"] == panel["trade_date"].max()]
    wl = latest[(latest["result_type"] == RESULT_STOCK) & (latest["is_watchlist"])]
    print(f"\n最新交易日 {panel['trade_date'].max()} | 次日关注 {len(wl)} 只")
    show = ["ts_code", "name", "board_type", "watch_reason", "inst_net", "hotmoney_net"]
    show = [c for c in show if c in wl.columns]
    print(wl.head(15)[show].to_string(index=False))


if __name__ == "__main__":
    main()
