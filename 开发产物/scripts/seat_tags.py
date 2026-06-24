#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUILD-B7 席位标签库（核心资产）
================================================================
把龙虎榜 `agency`（营业部全称）映射为 (category, tag, note)。

category 五类（与 seat_analysis 参考口径一致，扩展 量化）：
  北向 / 机构 / 游资 / 量化 / 普通

匹配优先级：北向 > 机构 > 标签库（游资/量化）> 普通。

设计原则：
  1. 北向、机构 用确定性关键词（"沪股通专用/深股通专用"、"机构专用"），零歧义。
  2. 游资 / 量化 用 **可维护的种子库** SEAT_LIBRARY（子串匹配）。这是一份「起点种子」，
     席位与游资的对应关系会随时间变动，使用方应持续维护、核对，不可当作永久真值。
  3. 支持外部覆盖：环境变量 B7_SEAT_OVERRIDE 指向一个 JSON 文件，
     格式 [{"match": "子串", "category": "游资", "tag": "宁波桑田路", "note": "..."}]，
     覆盖项优先于内置库（同一 agency 命中多条时取最长匹配子串）。

注意：本库为公开游资复盘圈广为流传的活跃席位整理，仅供量化研究参考，不构成对任何
个人/机构的指认，更不构成投资建议。数据以 PandaData 实际返回的 agency 为准。
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

# 北向 / 机构 确定性规则（子串）
NORTH_KEYS = ["沪股通专用", "深股通专用", "沪股通", "深股通", "港股通"]
INST_KEYS = ["机构专用"]

# 席位标签种子库：子串 → 标签。子串越具体越优先（按长度排序匹配）。
# category: 游资 / 量化。tag: 席位俗称。note: 简短说明。
SEAT_LIBRARY: list[dict] = [
    # —— 顶级/知名游资活跃席位（公开复盘常见）——
    {"match": "上海溧阳路", "category": "游资", "tag": "中信溧阳路", "note": "知名顶级游资活跃席位"},
    {"match": "益田路荣超商务中心", "category": "游资", "tag": "华泰益田路荣超", "note": "深圳顶级游资席位"},
    {"match": "深圳益田路", "category": "游资", "tag": "深圳益田路", "note": "深圳活跃游资席位"},
    {"match": "宁波桑田路", "category": "游资", "tag": "国盛宁波桑田路", "note": "宁波系顶级游资"},
    {"match": "宁波解放南路", "category": "游资", "tag": "光大宁波解放南路", "note": "宁波系活跃席位"},
    {"match": "宁波中山西路", "category": "游资", "tag": "宁波中山西路", "note": "宁波系活跃席位"},
    {"match": "欢乐海岸", "category": "游资", "tag": "中泰深圳欢乐海岸", "note": "顶级游资活跃席位"},
    {"match": "杭州上塘路", "category": "游资", "tag": "财通杭州上塘路", "note": "知名游资席位"},
    {"match": "杭州庆春路", "category": "游资", "tag": "杭州庆春路", "note": "浙系活跃席位"},
    {"match": "深圳金田路", "category": "游资", "tag": "银河深圳金田路", "note": "知名游资席位"},
    {"match": "深圳红岭中路", "category": "游资", "tag": "深圳红岭中路", "note": "深圳活跃席位"},
    {"match": "深圳泰然九路", "category": "游资", "tag": "深圳泰然九路", "note": "深圳活跃席位"},
    {"match": "上海江苏路", "category": "游资", "tag": "国君上海江苏路", "note": "知名活跃席位"},
    {"match": "上海武进路", "category": "游资", "tag": "上海武进路", "note": "活跃席位"},
    {"match": "三亚迎宾路", "category": "游资", "tag": "佛山系(三亚迎宾路)", "note": "佛山系一线游资席位"},
    {"match": "中山东路", "category": "游资", "tag": "中山东路", "note": "一线游资席位"},
    {"match": "前滩大道", "category": "游资", "tag": "上海前滩大道", "note": "一线游资席位"},
    {"match": "福州五一北路", "category": "游资", "tag": "福州五一北路", "note": "活跃席位"},
    {"match": "拉萨金融城南环路", "category": "游资", "tag": "东财拉萨金融城南环路", "note": "东财拉萨通道"},
    {"match": "深圳分公司", "category": "游资", "tag": "深圳系", "note": "深圳活跃通道"},
    {"match": "广州天河北路", "category": "游资", "tag": "广州天河北路", "note": "活跃席位"},
    {"match": "南京太平南路", "category": "游资", "tag": "南京太平南路", "note": "活跃席位"},
    {"match": "深圳福华一路", "category": "游资", "tag": "深圳福华一路", "note": "活跃席位"},
    {"match": "杭州解放东路", "category": "游资", "tag": "杭州解放东路", "note": "浙系活跃席位"},
    {"match": "苏州工业园区", "category": "游资", "tag": "苏州工业园区", "note": "活跃席位"},
    {"match": "上海浦东南路", "category": "游资", "tag": "上海浦东南路", "note": "活跃席位"},
    {"match": "西藏东方财富", "category": "游资", "tag": "东财西藏系", "note": "东财通道"},
    {"match": "深圳益田路荣超商务中心", "category": "游资", "tag": "华泰益田路荣超", "note": "深圳顶级游资席位"},
    # —— 量化/程序化常见通道补充 ——
    {"match": "中国国际金融", "category": "量化", "tag": "中金量化", "note": "量化/程序化常用通道"},
    {"match": "中信证券股份有限公司上海分公司", "category": "量化", "tag": "中信上海分公司", "note": "量化/机构大通道"},
    {"match": "摩根士丹利", "category": "量化", "tag": "摩根士丹利", "note": "外资量化通道"},
    {"match": "摩根大通", "category": "量化", "tag": "摩根大通", "note": "外资量化通道"},
    {"match": "高盛", "category": "量化", "tag": "高盛通道", "note": "外资量化通道"},
    {"match": "瑞银", "category": "量化", "tag": "瑞银通道", "note": "外资通道"},
    {"match": "瑞士信贷", "category": "量化", "tag": "瑞信通道", "note": "外资通道"},
    {"match": "野村", "category": "量化", "tag": "野村通道", "note": "外资通道"},
    {"match": "成都北一环", "category": "游资", "tag": "华西成都北一环", "note": "成都系活跃席位"},
    {"match": "成都东大街", "category": "游资", "tag": "成都东大街", "note": "成都系活跃席位"},
    {"match": "成都南一环", "category": "游资", "tag": "成都南一环", "note": "成都系活跃席位"},
    {"match": "绍兴", "category": "游资", "tag": "银河绍兴", "note": "历史知名游资席位"},
    {"match": "佛山", "category": "游资", "tag": "佛山系", "note": "佛山地域游资"},
    {"match": "温州", "category": "游资", "tag": "温州帮", "note": "温州地域游资"},
    {"match": "义乌", "category": "游资", "tag": "义乌帮", "note": "浙系地域游资"},
    {"match": "厦门厦禾路", "category": "游资", "tag": "厦门厦禾路", "note": "活跃席位"},
    {"match": "北京西三环中路", "category": "游资", "tag": "北京西三环中路", "note": "活跃席位"},
    {"match": "无锡清扬路", "category": "游资", "tag": "无锡清扬路", "note": "活跃席位"},
    # —— 拉萨系（东方财富散户/小资金/通道，亦有游资借道）——
    {"match": "东方财富证券股份有限公司拉萨", "category": "游资", "tag": "东财拉萨系", "note": "东财拉萨通道（散户/游资混杂）"},
    {"match": "拉萨团结路", "category": "游资", "tag": "东财拉萨团结路", "note": "东财拉萨通道"},
    {"match": "拉萨东环路", "category": "游资", "tag": "东财拉萨东环路", "note": "东财拉萨通道"},
    {"match": "拉萨金珠西路", "category": "游资", "tag": "东财拉萨金珠西路", "note": "东财拉萨通道"},
    {"match": "拉萨", "category": "游资", "tag": "拉萨系", "note": "拉萨通道席位"},
    # —— 量化/程序化常见通道（不确定性高，标注谨慎）——
    {"match": "华鑫证券有限责任公司上海分公司", "category": "量化", "tag": "华鑫上海分公司", "note": "量化/程序化常用通道"},
    {"match": "华鑫证券", "category": "量化", "tag": "华鑫席位", "note": "量化通道常见"},
    {"match": "国泰君安证券股份有限公司总部", "category": "量化", "tag": "国君总部", "note": "总部/量化通道"},
    {"match": "中信证券股份有限公司总部", "category": "量化", "tag": "中信总部", "note": "总部/量化通道"},
]

# 按 match 子串长度降序，保证最具体的先命中
_SORTED_LIB = sorted(SEAT_LIBRARY, key=lambda d: len(d["match"]), reverse=True)


@lru_cache(maxsize=1)
def _overrides() -> list[dict]:
    path = os.getenv("B7_SEAT_OVERRIDE")
    if not path or not os.path.exists(path):
        return []
    try:
        data = json.loads(open(path, encoding="utf-8").read())
        return sorted([d for d in data if "match" in d], key=lambda d: len(d["match"]), reverse=True)
    except Exception:
        return []


def match_seat(agency: Optional[str]) -> dict:
    """把营业部名映射为 {category, tag, note}。"""
    a = str(agency or "").strip()
    if not a:
        return {"category": "普通", "tag": "", "note": ""}
    # 1) 北向
    if any(k in a for k in NORTH_KEYS):
        return {"category": "北向", "tag": "北向资金", "note": "沪深股通专用"}
    # 2) 机构
    if any(k in a for k in INST_KEYS):
        return {"category": "机构", "tag": "机构专用", "note": "机构席位"}
    # 3) 外部覆盖优先，其次内置种子库（最长子串优先）
    for d in _overrides() + _SORTED_LIB:
        if d["match"] in a:
            return {"category": d.get("category", "游资"), "tag": d.get("tag", d["match"]),
                    "note": d.get("note", "")}
    # 4) 其他具名券商席位 → 营业部（游资/大户活跃席位，只是未在种子库标注）。
    #    龙虎榜能进买卖前五的营业部本身即显著资金，归"营业部"而非"普通"，避免游资盘被漏统计。
    if any(k in a for k in BRANCH_KEYS):
        return {"category": "营业部", "tag": "", "note": "具名营业部席位（未标注，建议补入种子库）"}
    # 5) 兜底（无法识别的异常名）
    return {"category": "普通", "tag": "", "note": ""}


# 具名券商席位关键词：命中即视为营业部资金（游资/大户）
BRANCH_KEYS = ["营业部", "分公司", "证券总部", "自营"]

# 游资盘口径：知名游资(种子库) + 其他具名营业部
HOTMONEY_CATS = ["游资", "营业部"]


def is_known_hotmoney(agency: Optional[str]) -> bool:
    """是否为标签库命中的知名游资席位（不含未标注营业部）。"""
    return match_seat(agency)["category"] == "游资"


def is_hotmoney_desk(agency: Optional[str]) -> bool:
    """是否为游资盘席位（知名游资 + 其他具名营业部，即非机构/非北向的活跃资金）。"""
    return match_seat(agency)["category"] in HOTMONEY_CATS


def library_size() -> dict:
    return {"seed": len(SEAT_LIBRARY), "override": len(_overrides())}


if __name__ == "__main__":
    samples = [
        "机构专用", "沪股通专用", "深股通专用",
        "中信证券股份有限公司上海溧阳路证券营业部",
        "国盛证券有限责任公司宁波桑田路证券营业部",
        "东方财富证券股份有限公司拉萨团结路第二证券营业部",
        "华鑫证券有限责任公司上海分公司",
        "招商证券股份有限公司深圳福民路证券营业部",
    ]
    for s in samples:
        m = match_seat(s)
        print(f"{m['category']:>4} | {m['tag'] or '—':<16} | {s}")
    print("库规模:", library_size())
