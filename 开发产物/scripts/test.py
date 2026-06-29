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
       A 600000.SH：机构买1.2亿 + 宁波桑田路(游资)买0.8亿；卖方机构0.3亿 → 机构+游资净买
       B 300001.SZ：东财拉萨(游资)买0.5亿；卖方游资0.6亿 → 游资净卖
    """
    buy = [
        {"symbol": "600000.SH", "date": "20260619", "side": "buy", "rank": 1, "agency": "机构专用", "b_value": 1.2e8, "s_value": 0, "reason": "日涨幅偏离7%"},
        {"symbol": "600000.SH", "date": "20260619", "side": "buy", "rank": 2, "agency": "国盛证券有限责任公司宁波桑田路证券营业部", "b_value": 0.8e8, "s_value": 0, "reason": "日涨幅偏离7%"},
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
    # 宁波桑田路：爬取映射或种子库均判为游资
    assert seat_tags.match_seat("国盛证券有限责任公司宁波桑田路证券营业部")["category"] == "游资"
    # 未在任何库的具名营业部 → 营业部（非普通），避免游资盘漏统计
    assert seat_tags.match_seat("招商证券股份有限公司深圳福民路证券营业部")["category"] == "营业部"
    assert seat_tags.is_hotmoney_desk("招商证券股份有限公司深圳福民路证券营业部")
    assert seat_tags.is_known_hotmoney("国盛证券有限责任公司宁波桑田路证券营业部")
    # 真正的普通（无营业部/分公司等关键词）
    assert seat_tags.match_seat("某不明资金")["category"] == "普通"
    print("✅ test_seat_tags（机构/北向/游资/量化/营业部/普通）")


def test_seat_library_json():
    """席位库从 seat_library.json + 爬取映射 seat_yyb_map.json 加载。"""
    sz = seat_tags.library_size()
    assert sz["seeds"] >= 40 and sz["seed_游资"] >= 30, sz
    assert sz["yyb_map"] >= 200, sz  # 爬取的营业部精确映射
    g = seat_tags.groups()
    assert "宁波系" in g and "深圳帮" in g, g
    print(f"✅ test_seat_library_json（种子 {sz['seeds']} + 爬取映射 {sz['yyb_map']} 营业部，帮派 {len(g)} 类）")


def test_seat_yyb_map():
    """爬取的营业部精确映射：命中带游资本尊 alias + 置信度。"""
    m = seat_tags.match_seat("国盛证券有限责任公司宁波桑田路证券营业部")
    assert m["alias"], m                       # 拿到游资本尊/帮派名号
    assert m["confidence"] in ("A-高", "B-中", "C-低"), m
    # 量化集群（如三板组/量化打板）归量化
    cats = {seat_tags.match_seat(k)["category"] for k in [
        "信达证券股份有限公司温州瓯江路证券营业部"]}
    assert cats <= {"游资", "量化", "营业部"}, cats
    print(f"✅ test_seat_yyb_map（精确映射带本尊 alias + 置信度，样例 alias={m['alias']}/{m['confidence']}）")


def test_build_pool_nets():
    pool = build_pool(validate_input(_fetched()), names={"600000.SH": "测试A", "300001.SZ": "测试B"})
    a = pool[pool["ts_code"] == "600000.SH"].iloc[0]
    assert abs(a["inst_net"] - (1.2e8 - 0.3e8)) < 1, a["inst_net"]      # 机构净买 0.9 亿
    assert abs(a["hotmoney_net"] - 0.8e8) < 1, a["hotmoney_net"]         # 游资净买 0.8 亿
    assert "宁波桑田路" in a["hotmoney_seats"], a["hotmoney_seats"]
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
    assert "次日关注清单" in md and "营业部合集" in md and "宁波桑田路" in md
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


def test_single_side_day():
    """单边日（仅买方 / 仅卖方）不得崩溃（验收报告 B7 缺陷①：object dtype 致 b_value-s_value TypeError）。"""
    buy_only = {"list": [], "sell": [], "buy": [
        {"symbol": "600000.SH", "date": "20260619", "side": "buy", "rank": 1,
         "agency": "机构专用", "b_value": 1.2e8, "s_value": 0, "reason": "涨幅偏离7%"},
        {"symbol": "600000.SH", "date": "20260619", "side": "buy", "rank": 2,
         "agency": "国盛证券有限责任公司宁波桑田路证券营业部", "b_value": 0.8e8, "s_value": 0, "reason": "涨幅偏离7%"},
    ]}
    out = run(buy_only, config={"names": {"600000.SH": "测试A"}})
    a = out[out["ts_code"] == "600000.SH"].iloc[0]
    assert abs(a["inst_net"] - 1.2e8) < 1, a["inst_net"]
    assert abs(a["hotmoney_net"] - 0.8e8) < 1, a["hotmoney_net"]

    sell_only = {"list": [], "buy": [], "sell": [
        {"symbol": "300001.SZ", "date": "20260619", "side": "sell", "rank": 1,
         "agency": "国盛证券有限责任公司宁波桑田路证券营业部", "b_value": 0, "s_value": 0.6e8, "reason": "换手20%"},
    ]}
    out2 = run(sell_only, config={"names": {"300001.SZ": "测试B"}})
    b = out2[out2["ts_code"] == "300001.SZ"].iloc[0]
    assert b["hotmoney_net"] < 0, b["hotmoney_net"]
    print("✅ test_single_side_day（仅买/仅卖单边日不崩溃，净额方向正确）")


def test_city_key_no_false_positive():
    """裸地名键收紧（验收报告 B7 缺陷②）：同城他券商营业部不得被误标为某具名游资。"""
    # 误标样例 → 应落"营业部"（仍计入游资盘，但不冒认具名游资）
    for ag in ["国泰君安证券股份有限公司绍兴营业部",
               "广发证券股份有限公司佛山分公司",
               "某证券义乌稠城营业部",
               "中信证券股份有限公司拉萨营业部"]:
        assert seat_tags.match_seat(ag)["category"] == "营业部", ag
    # 真正的具名游资仍命中（绍兴=种子 AND 匹配；三亚迎宾路=高置信爬取映射）
    assert seat_tags.match_seat("中国银河证券股份有限公司绍兴营业部")["tag"] == "银河绍兴"
    fs = seat_tags.match_seat("国泰海通证券股份有限公司三亚迎宾路证券营业部")
    assert fs["category"] == "游资" and "佛山" in fs["tag"], fs
    # 东财拉萨 street 级 curated 映射不被 C-低 爬取条目覆盖
    m = seat_tags.match_seat("东方财富证券股份有限公司拉萨团结路第二证券营业部")
    assert m["category"] == "游资" and "拉萨" in m["tag"], m
    print("✅ test_city_key_no_false_positive（裸地名误标已修，具名/AND 匹配仍命中）")


def test_real_data_optional():
    try:
        out = maintain_daily()
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if any(k in msg for k in ("500009", "单日总流量", "200103", "权限", "环境变量", "ServiceError",
                                   "504", "无法导入", "panda_data", "pip")):
            print(f"⏭️  test_real_data_optional 跳过（配额/权限/服务/凭证/未装 SDK）：{msg[:60]}")
            return
        raise
    if out.empty:
        print("⏭️  test_real_data_optional：当日无龙虎榜（可能非交易日）")
        return
    assert {"trade_date", "build_id", "target_id"} <= set(out.columns)
    print(f"✅ test_real_data_optional（真实龙虎榜 {len(out)} 行）")


if __name__ == "__main__":
    test_seat_tags()
    test_seat_library_json()
    test_seat_yyb_map()
    test_build_pool_nets()
    test_watchlist()
    test_standard_and_summary()
    test_render()
    test_multi_reason_breakdown()
    test_stock_detail_and_range()
    test_interactive_html()
    test_empty_and_missing()
    test_single_side_day()
    test_city_key_no_false_positive()
    test_real_data_optional()
    print("\n🎉 全部测试通过")
