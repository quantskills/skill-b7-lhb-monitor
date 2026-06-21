#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUILD-B7 龙虎榜监控+席位标签库 —— 测试脚本
覆盖：席位标签匹配 / 个股聚合(机构·游资·北向净额) / 次日清单打分 / 标准列+JSON /
     渲染(markdown+html) / 空输入 / 缺字段 / 真实数据(配额超限自动跳过)。
运行：python scripts/test.py
"""
from __future__ import annotations

import json

import pandas as pd

import seat_tags
from build import (
    backfill, board_type_of, build_pool, compute_watchlist, fetch_lhb, maintain_daily,
    range_stats, run, to_standard_output, validate_input,
)
from render import render_markdown, render_range_stats, render_stock_detail
from render_html import render_html, render_range_html


# ---------- 合成龙虎榜数据 ----------
def _fetched():
    """两只票：
       A 600000.SH：机构买1.2亿 + 中信溧阳路(游资)买0.8亿；卖方机构0.3亿 → 机构+游资净买
       B 300001.SZ：东财拉萨(游资)买0.5亿；卖方游资0.6亿 → 游资净卖
    """
    buy = [
        {"symbol": "600000.SH", "date": "20260619", "side": "buy", "rank": 1, "agency": "机构专用", "b_value": 1.2e8, "s_value": 0, "reason": "日涨幅偏离7%"},
        {"symbol": "600000.SH", "date": "20260619", "side": "buy", "rank": 2, "agency": "中信证券股份有限公司上海溧阳路证券营业部", "b_value": 0.8e8, "s_value": 0, "reason": "日涨幅偏离7%"},
        {"symbol": "300001.SZ", "date": "20260619", "side": "buy", "rank": 1, "agency": "东方财富证券股份有限公司拉萨团结路第二证券营业部", "b_value": 0.5e8, "s_value": 0, "reason": "日换手率20%"},
    ]
    sell = [
        {"symbol": "600000.SH", "date": "20260619", "side": "sell", "rank": 1, "agency": "机构专用", "b_value": 0, "s_value": 0.3e8, "reason": "日涨幅偏离7%"},
        {"symbol": "300001.SZ", "date": "20260619", "side": "sell", "rank": 1, "agency": "国盛证券有限责任公司宁波桑田路证券营业部", "b_value": 0, "s_value": 0.6e8, "reason": "日换手率20%"},
    ]
    lst = [
        {"symbol": "600000.SH", "date": "20260619", "type": "G0007", "reason": "日涨幅偏离值达7%", "amount": 5e8, "change_rate": 0.10, "turnover": 0.15},
        {"symbol": "300001.SZ", "date": "20260619", "type": "T0020", "reason": "日换手率达20%", "amount": 4e8, "change_rate": 0.05, "turnover": 0.25},
    ]
    return {"list": lst, "buy": buy, "sell": sell}


# ---------- 测试 ----------
def test_seat_tags():
    assert seat_tags.match_seat("机构专用")["category"] == "机构"
    assert seat_tags.match_seat("深股通专用")["category"] == "北向"
    m = seat_tags.match_seat("中信证券股份有限公司上海溧阳路证券营业部")
    assert m["category"] == "游资" and m["tag"] == "中信溧阳路", m
    assert seat_tags.match_seat("华鑫证券有限责任公司上海分公司")["category"] == "量化"
    assert seat_tags.match_seat("招商证券股份有限公司深圳福民路证券营业部")["category"] == "普通"
    assert seat_tags.is_known_hotmoney("国盛证券有限责任公司宁波桑田路证券营业部")
    print("✅ test_seat_tags（机构/北向/游资/量化/普通 五类）")


def test_build_pool_nets():
    pool = build_pool(validate_input(_fetched()), names={"600000.SH": "测试A", "300001.SZ": "测试B"})
    a = pool[pool["ts_code"] == "600000.SH"].iloc[0]
    assert abs(a["inst_net"] - (1.2e8 - 0.3e8)) < 1, a["inst_net"]      # 机构净买 0.9 亿
    assert abs(a["hotmoney_net"] - 0.8e8) < 1, a["hotmoney_net"]         # 游资净买 0.8 亿
    assert "中信溧阳路" in a["hotmoney_seats"], a["hotmoney_seats"]
    b = pool[pool["ts_code"] == "300001.SZ"].iloc[0]
    assert b["hotmoney_net"] < 0, b["hotmoney_net"]                      # 游资净卖
    print("✅ test_build_pool_nets（机构0.9亿/游资0.8亿净买，B游资净卖）")


def test_watchlist():
    out = run(_fetched(), config={"names": {"600000.SH": "测试A", "300001.SZ": "测试B"}})
    stocks = out[out["result_type"] == "lhb_stock"]
    a = stocks[stocks["ts_code"] == "600000.SH"].iloc[0]
    b = stocks[stocks["ts_code"] == "300001.SZ"].iloc[0]
    assert bool(a["is_watchlist"]), "机构+游资净买的 A 应入选次日清单"
    assert a["watchlist_rank"] < b["watchlist_rank"], "A 打分应高于 B"
    assert "机构净买" in a["watch_reason"], a["watch_reason"]
    json.loads(a["result_json"])
    print("✅ test_watchlist（A 入选次日清单/排名高/理由含机构净买）")


def test_standard_and_summary():
    out = run(_fetched())
    assert {"trade_date", "build_id", "target_id", "result_type", "result_value", "result_json"} <= set(out.columns)
    summ = out[out["result_type"] == "lhb_summary"]
    assert len(summ) == 1
    s = json.loads(summ.iloc[0]["result_json"])
    assert s["n_lhb"] == 2 and s["n_inst_buy"] >= 1
    assert "seat_library" in s
    # 所有 result_json 可解析
    for j in out["result_json"]:
        json.loads(j)
    print("✅ test_standard_and_summary（标准列+市场汇总行+JSON 全可解析）")


def test_render():
    out = run(_fetched(), config={"names": {"600000.SH": "测试A", "300001.SZ": "测试B"}})
    md = render_markdown(out)
    assert "次日关注清单" in md and "游资席位合集" in md and "中信溧阳路" in md
    h = render_html(out)
    assert "<html" in h and "龙虎榜监控" in h
    print("✅ test_render（次日清单/机构合集/游资席位合集 + HTML）")


def test_empty_and_missing():
    try:
        run(None)
    except ValueError:
        pass
    else:
        raise AssertionError("None 输入必须抛 ValueError")
    try:
        run([{"date": "20260619"}])  # 缺 agency / symbol
    except ValueError as e:
        assert "缺少必要字段" in str(e)
    else:
        raise AssertionError("缺字段必须抛 ValueError")
    print("✅ test_empty_and_missing")


def _multi_reason_fetched():
    """600000.SH 同日两条上榜原因(G0007 涨幅偏离 / T0020 换手)，各自一组买卖营业部。"""
    buy = [
        {"symbol": "600000.SH", "date": "20260619", "side": "buy", "type": "G0007", "rank": 1, "agency": "机构专用", "b_value": 1.0e8, "s_value": 0, "reason": "日涨幅偏离值达7%"},
        {"symbol": "600000.SH", "date": "20260619", "side": "buy", "type": "T0020", "rank": 1, "agency": "中信证券股份有限公司上海溧阳路证券营业部", "b_value": 0.6e8, "s_value": 0.1e8, "reason": "日换手率达20%"},
    ]
    sell = [
        {"symbol": "600000.SH", "date": "20260619", "side": "sell", "type": "G0007", "rank": 1, "agency": "国盛证券有限责任公司宁波桑田路证券营业部", "b_value": 0, "s_value": 0.4e8, "reason": "日涨幅偏离值达7%"},
    ]
    return {"list": [], "buy": buy, "sell": sell}


def test_multi_reason_breakdown():
    out = run(_multi_reason_fetched(), config={"names": {"600000.SH": "测试A"}})
    r = out[out["ts_code"] == "600000.SH"].iloc[0]
    j = json.loads(r["result_json"])
    assert j["n_reasons"] == 2, j["n_reasons"]
    types = {x["type"] for x in j["reasons"]}
    assert types == {"G0007", "T0020"}, types
    # 每个原因都带买入/卖出营业部组
    for rs in j["reasons"]:
        assert "buy" in rs and "sell" in rs and "buy_total" in rs
    # 席位带 b 和 s 双金额
    seat = j["reasons"][0]["buy"][0]
    assert "b" in seat and "s" in seat
    print("✅ test_multi_reason_breakdown（2 条上榜原因各自拆买卖营业部，席位带双金额）")


def test_stock_detail_and_range():
    out = run(_multi_reason_fetched(), config={"names": {"600000.SH": "测试A"}})
    md = render_stock_detail(out, "600000.SH")
    assert "上榜原因" in md and "买入营业部" in md and "中信证券" in md
    h = render_range_html(out, "600000.SH")
    assert "区间统计" in h
    # range_stats 聚合
    rs = range_stats(out, "600000.SH")
    assert rs["n_days"] == 1 and len(rs["seats"]) >= 2
    # 机构专用 应为净买最大席位之一
    insts = [s for s in rs["seats"] if s["category"] == "机构"]
    assert insts and insts[0]["net"] > 0
    print(f"✅ test_stock_detail_and_range（个股详情页 + 区间统计 {len(rs['seats'])} 席位）")


def test_interactive_html():
    out = run(_fetched(), config={"names": {"600000.SH": "测试A", "300001.SZ": "测试B"}})
    h = render_html(out)
    # 交互元素存在
    for token in ["DATA =", 'data-tab="stock"', 'id="q"', "stockRows", "营业部合集", "上榜原因"]:
        assert token in h, token
    print("✅ test_interactive_html（内嵌数据 + tab/搜索/排序/展开详情 JS）")


def test_real_data_optional():
    try:
        out = maintain_daily()
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if any(k in msg for k in ("500009", "单日总流量", "200103", "权限", "环境变量", "ServiceError", "504")):
            print(f"⏭️  test_real_data_optional 跳过（配额/权限/服务/凭证）：{msg[:60]}")
            return
        raise
    if out.empty:
        print("⏭️  test_real_data_optional：当日无龙虎榜（可能非交易日）")
        return
    assert {"trade_date", "build_id", "target_id"} <= set(out.columns)
    print(f"✅ test_real_data_optional（真实龙虎榜 {len(out)} 行）")


if __name__ == "__main__":
    test_seat_tags()
    test_build_pool_nets()
    test_watchlist()
    test_standard_and_summary()
    test_render()
    test_multi_reason_breakdown()
    test_stock_detail_and_range()
    test_interactive_html()
    test_empty_and_missing()
    test_real_data_optional()
    print("\n🎉 全部测试通过")
