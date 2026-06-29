#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUILD-B7 席位标签库（核心资产）
================================================================
把龙虎榜 `agency`（营业部全称）映射为 (category, tag, group, tier, alias, note)。

数据源：同目录 `seat_library.json`（独立可维护的常见游资席位库，按帮派/级别组织）。
找不到 JSON 时退化到内置最小规则（仅北向/机构/营业部），保证可运行。

category 六类：北向 / 机构 / 游资 / 量化 / 营业部 / 普通
  匹配优先级：北向 > 机构 > 库(游资/量化，最长子串优先) > 营业部(具名券商席位兜底) > 普通

字段：
  tag   席位俗称（中信溧阳路…）
  group 帮派/地域（上海帮/深圳帮/宁波系/成都系/佛山系/拉萨系/温州帮/量化通道/外资通道…）
  tier  级别（一线/二线）
  alias 游资本尊名号（默认空，由使用方核实后填，如"赵老哥"/"章盟主"；本库不臆造民间传闻）

外部覆盖：环境变量 B7_SEAT_OVERRIDE 指向 JSON 列表
  [{"match","category","tag","group","tier","alias","note"}]，优先于内置库（最长子串优先）。

声明：本库为公开复盘常识整理，仅供量化研究参考，会随时间变动需持续维护，
不构成对任何个人/机构的指认，更不构成投资建议。数据以 PandaData 返回的 agency 为准。
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

_LIB_PATH = Path(__file__).resolve().parent / "seat_library.json"
_YYB_MAP_PATH = Path(__file__).resolve().parent / "seat_yyb_map.json"

# 内置最小兜底（JSON 缺失时用）
_FALLBACK = {
    "rules": {"north": ["沪股通专用", "深股通专用", "沪股通", "深股通", "港股通"],
              "inst": ["机构专用"], "branch": ["营业部", "分公司", "证券总部", "自营"]},
    "seats": [],
}

# 游资盘口径：知名游资(库) + 其他具名营业部
HOTMONEY_CATS = ["游资", "营业部"]


@lru_cache(maxsize=1)
def _lib() -> dict:
    try:
        data = json.loads(_LIB_PATH.read_text(encoding="utf-8"))
        data.setdefault("rules", _FALLBACK["rules"])
        data.setdefault("seats", [])
        return data
    except Exception:
        return _FALLBACK


def _match_len(m) -> int:
    """match 的总字符长度（list 形态=各 token 长度之和），用于"最具体优先"排序。"""
    if isinstance(m, (list, tuple)):
        return sum(len(str(t)) for t in m)
    return len(str(m or ""))


def _match_hit(m, a: str) -> bool:
    """命中判定：字符串=子串包含；list=所有 token 均为子串。
    list 形态用于"券商+地名"AND 匹配（如 ["银河","绍兴"]），避免裸地名键把
    同城任意券商营业部误标为某具名游资。"""
    if isinstance(m, (list, tuple)):
        return bool(m) and all(str(t) in a for t in m)
    return bool(m) and str(m) in a


@lru_cache(maxsize=1)
def _sorted_seats() -> list[dict]:
    """库内席位按 match 长度降序，最具体优先（list 形态按 token 长度之和）。"""
    return sorted(_lib().get("seats", []), key=lambda d: _match_len(d.get("match", "")), reverse=True)


@lru_cache(maxsize=1)
def _yyb_map() -> dict:
    """爬取的「营业部全称 → 游资标签」精确映射（build_seat_map.py 生成）。"""
    try:
        return json.loads(_YYB_MAP_PATH.read_text(encoding="utf-8")).get("map", {})
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _overrides() -> list[dict]:
    path = os.getenv("B7_SEAT_OVERRIDE")
    if not path or not os.path.exists(path):
        return []
    try:
        data = json.loads(open(path, encoding="utf-8").read())
        return sorted([d for d in data if "match" in d], key=lambda d: _match_len(d["match"]), reverse=True)
    except Exception:
        return []


def _entry(d: dict) -> dict:
    m = d.get("match", "")
    default_tag = "".join(str(t) for t in m) if isinstance(m, (list, tuple)) else m
    return {"category": d.get("category", "游资"), "tag": d.get("tag", default_tag),
            "group": d.get("group", ""), "tier": d.get("tier", ""),
            "alias": d.get("alias", ""), "confidence": d.get("confidence", ""),
            "note": d.get("note", "")}


def _blank(category: str, tag: str = "", note: str = "") -> dict:
    return {"category": category, "tag": tag, "group": "", "tier": "", "alias": "",
            "confidence": "", "note": note}


def _from_yyb(hit: dict) -> dict:
    return {"category": hit.get("category", "游资"), "tag": hit.get("tag", ""),
            "group": hit.get("group", ""), "tier": "", "alias": hit.get("alias", ""),
            "confidence": hit.get("confidence", ""),
            "note": f"爬取映射·{hit.get('confidence','')}·最近 {hit.get('last_seen','')}"}


def match_seat(agency: Optional[str]) -> dict:
    """营业部名 → {category, tag, group, tier, alias, confidence, note}。
    优先级：北向 > 机构 > 外部覆盖 > 爬取精确映射(高/中置信) > 子串种子库(curated) >
    爬取精确映射(C-低/无置信兜底) > 营业部兜底 > 普通。
    说明：C-低 单次观测的爬取条目可信度低，让位于人工 curated 的种子库 street 级映射，
    避免如「东财拉萨团结路」被一条 C-低 爬取误标为「宁波桑田路」。"""
    a = str(agency or "").strip()
    if not a:
        return _blank("普通")
    rules = _lib().get("rules", _FALLBACK["rules"])
    # 1) 北向
    if any(k in a for k in rules.get("north", [])):
        return _blank("北向", "北向资金", "沪深股通专用")
    # 2) 机构
    if any(k in a for k in rules.get("inst", [])):
        return _blank("机构", "机构专用", "机构席位")
    # 3) 外部覆盖（最长子串优先）
    for d in _overrides():
        if _match_hit(d.get("match"), a):
            return _entry(d)
    # 4) 爬取精确映射（营业部全称完全匹配）——高/中置信优先于种子库
    hit = _yyb_map().get(a)
    if hit and hit.get("confidence", "") not in ("C-低", ""):
        return _from_yyb(hit)
    # 5) 子串种子库（curated，最长子串优先；list 形态=券商+地名 AND 匹配）
    for d in _sorted_seats():
        if _match_hit(d.get("match"), a):
            return _entry(d)
    # 6) 低置信(C-低/无)爬取映射兜底——无种子命中时仍给出（带 C-低 标注供使用方甄别）
    if hit:
        return _from_yyb(hit)
    # 7) 其他具名券商席位 → 营业部（游资/大户活跃席位，未在库标注）
    if any(k in a for k in rules.get("branch", _FALLBACK["rules"]["branch"])):
        return _blank("营业部", "", "具名营业部席位（未标注，建议补入席位库）")
    # 8) 兜底
    return _blank("普通")


def is_known_hotmoney(agency: Optional[str]) -> bool:
    """是否为库命中的知名游资席位（不含未标注营业部）。"""
    return match_seat(agency)["category"] == "游资"


def is_hotmoney_desk(agency: Optional[str]) -> bool:
    """是否为游资盘席位（知名游资 + 其他具名营业部）。"""
    return match_seat(agency)["category"] in HOTMONEY_CATS


def library_size() -> dict:
    seats = _lib().get("seats", [])
    n_hot = sum(1 for s in seats if s.get("category") == "游资")
    n_quant = sum(1 for s in seats if s.get("category") == "量化")
    ymap = _yyb_map()
    return {"seeds": len(seats), "seed_游资": n_hot, "seed_量化": n_quant,
            "yyb_map": len(ymap), "yyb_游资": sum(1 for v in ymap.values() if v.get("category") == "游资"),
            "yyb_量化": sum(1 for v in ymap.values() if v.get("category") == "量化"),
            "override": len(_overrides())}


def groups() -> dict:
    """各帮派席位数（用于看板/统计）。"""
    g: dict[str, int] = {}
    for s in _lib().get("seats", []):
        if s.get("category") == "游资" and s.get("group"):
            g[s["group"]] = g.get(s["group"], 0) + 1
    return dict(sorted(g.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    samples = [
        "机构专用", "深股通专用",
        "中信证券股份有限公司上海溧阳路证券营业部",
        "国盛证券有限责任公司宁波桑田路证券营业部",
        "国泰海通证券股份有限公司三亚迎宾路证券营业部",
        "东方财富证券股份有限公司拉萨团结路第二证券营业部",
        "高盛（中国）证券有限责任公司上海浦东新区世纪大道证券营业部",
        "招商证券股份有限公司深圳福民路证券营业部",
        "某不明资金",
    ]
    for s in samples:
        m = match_seat(s)
        extra = f"[{m['group']}·{m['tier']}]" if m["group"] else ""
        print(f"{m['category']:>4} | {m['tag'] or '—':<16}{extra:<14} | {s}")
    print("库规模:", library_size())
    print("帮派分布:", groups())
