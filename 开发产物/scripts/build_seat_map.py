#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B7 席位映射构建器：把爬取的「游资席位标签集锦」CSV 转成 seat_tags 可用的 seat_yyb_map.json
================================================================
输入：references/seat_data/youzi-seat-label-collection-*.csv
      （列：游资标签/标签类型/当前分组/营业部全称/置信度/独立观测次数/最近观测/当前元数据有效/匹配依据…）
输出：scripts/seat_yyb_map.json
      { 营业部全称: {category, tag(俗称/帮派), alias(游资本尊), group(标签类型), confidence,
                     obs(独立观测), last_seen, candidates:[其他候选标签]} }

去重：一个营业部可能对应多个游资标签 → 取最优候选（有效 > 置信度 A>B>C > 独立观测次数）。
分类：标签类型含「量化」→ category=量化；否则 game资。
重跑：使用方重新爬取后，把新 CSV 放进 references/seat_data/ 再跑本脚本即可刷新映射。

用法：python scripts/build_seat_map.py [--csv <path>] [--out <path>]
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SEAT_DATA = SCRIPTS.parent / "references" / "seat_data"
DEFAULT_OUT = SCRIPTS / "seat_yyb_map.json"

CONF_RANK = {"A-高": 3, "B-中": 2, "C-低": 1}


def _latest_csv() -> Path:
    cands = sorted(SEAT_DATA.glob("youzi-seat-label-collection-*.csv"))
    if not cands:
        raise SystemExit(f"未找到席位标签 CSV，请放入 {SEAT_DATA}/")
    return cands[-1]


def _to_int(s: str) -> int:
    try:
        return int(float(s))
    except Exception:
        return 0


def _category(label_type: str, tag: str) -> str:
    """标签类型含'量化'→量化；其余为游资。"""
    return "量化" if ("量化" in str(label_type)) else "游资"


def build(csv_path: Path) -> dict:
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    by_yyb: dict[str, list] = {}
    for r in rows:
        yyb = (r.get("营业部全称") or "").strip()
        if not yyb:
            continue
        by_yyb.setdefault(yyb, []).append(r)

    out = {}
    for yyb, cands in by_yyb.items():
        # 排序键：有效优先 > 置信度 > 独立观测次数 > 双源记录
        def key(r):
            valid = 1 if (r.get("当前元数据有效", "").startswith("是")) else 0
            return (valid, CONF_RANK.get(r.get("置信度", ""), 0),
                    _to_int(r.get("独立观测次数", "0")), _to_int(r.get("双源证据记录数", "0")))
        cands_sorted = sorted(cands, key=key, reverse=True)
        best = cands_sorted[0]
        tag = (best.get("游资标签") or "").strip()
        label_type = (best.get("标签类型") or "").strip()
        out[yyb] = {
            "category": _category(label_type, tag),
            "tag": tag,
            "alias": tag,                      # 游资本尊/帮派名号（来自爬取标签）
            "group": label_type,               # 标签类型：地域游资集群/游资别名路线/策略量化集群
            "subgroup": (best.get("当前分组") or "").strip(),
            "confidence": (best.get("置信度") or "").strip(),
            "obs": _to_int(best.get("独立观测次数", "0")),
            "last_seen": (best.get("最近观测") or "").strip(),
            "valid": best.get("当前元数据有效", "").startswith("是"),
            "candidates": sorted({(c.get("游资标签") or "").strip() for c in cands_sorted} - {tag}),
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="构建 seat_yyb_map.json")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    csv_path = Path(args.csv) if args.csv else _latest_csv()
    mapping = build(csv_path)
    meta = {
        "_source": csv_path.name,
        "_count": len(mapping),
        "_note": "由 build_seat_map.py 从爬取CSV生成；营业部全称→游资标签(alias)。游资别名为民间观测映射，"
                 "非券商官方身份，会随时间迁移，结合 confidence/last_seen 使用，不构成投资建议。",
    }
    payload = {"_meta": meta, "map": mapping}
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    cats = Counter(v["category"] for v in mapping.values())
    confs = Counter(v["confidence"] for v in mapping.values())
    print(f"已生成 {args.out}")
    print(f"  营业部映射: {len(mapping)} 个 | 分类: {dict(cats)} | 置信度: {dict(confs)}")


if __name__ == "__main__":
    main()
