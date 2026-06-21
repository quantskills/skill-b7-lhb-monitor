# B7 · 龙虎榜监控 + 席位标签库

> 收盘后自动抓取 A 股龙虎榜，用**席位标签库**匹配营业部（北向/机构/游资/量化/普通），
> 生成**次日关注清单**，每日整理**机构合集 / 游资席位合集 / 个股席位明细**，出暗色 HTML 看板。
> 数据源：PandaData。席位标签库为可维护种子库，支持外部覆盖。

---

## 一句话定位
今天龙虎榜谁上榜、机构买了啥、哪个游资出手、明天关注谁。

## 怎么说（自然语言触发）

| 你说 | 它做什么 |
|---|---|
| "跑一下今天龙虎榜" / "龙虎榜监控" | 抓榜+席位标签+次日清单+机构/游资合集 |
| "明天关注哪些票" | 次日关注清单（打分排序 + 上榜理由） |
| "今天机构买了啥" | 机构合集（机构净买排序） |
| "拉萨系 / 宁波桑田路 / XX游资 今天买了哪些" | 游资席位合集，按席位查标的 |
| "某某股票龙虎榜谁在买卖" / "看下天娱数科的龙虎榜" | **个股详情页**：按上榜原因拆分，每个原因列买入/卖出营业部表（带标签、双金额） |
| "某票最近 3 天/这一周龙虎榜区间统计" | **区间统计**：各营业部 总买/总卖/净额/上榜次数，按净额排序 |
| "出个龙虎榜 HTML 看板" | **交互式看板**：tab 切换(股票/机构/营业部)、搜索、筛选、列排序、点行展开个股详情 |
| "回填 6 月的龙虎榜" | 区间回填历史（区间统计依赖回填的历史） |

> 一只票一天可能有**多条上榜原因**（如同时涨幅偏离7% + 换手20%），每条原因对应各自一组买入/卖出营业部，详情页会分别列出。

## 可选参数（不说走默认）

| 参数 | 默认 | 怎么说 |
|---|---|---|
| 日期 | 最近有数据的交易日 | "看 6/18 的"（注意龙虎榜傍晚才公布，~19:30 后跑） |
| 输出 | 看问法 | "口头答 / 给表格 / 出 HTML 看板" |
| 席位库 | 内置种子库(~33) | "把 XX 营业部加成游资标签"→走 `B7_SEAT_OVERRIDE` 覆盖 |
| 打分权重 | 机构0.35/游资0.35/净买0.20/席位数0.10 | "更看重机构 / 更看重游资" |

## 命令行（手动跑）

```bash
export PANDA_USERNAME=<86手机号>; export PANDA_PASSWORD=<密码>
python 开发产物/scripts/build.py --mode daily                 # 当日维护（~19:30 后，龙虎榜才出）
python 开发产物/scripts/build.py --mode backfill --start 20260601 --end 20260618
python 开发产物/scripts/render.py                             # 每日整理（markdown）
python 开发产物/scripts/render.py --stock 002354.SZ           # 个股详情页（按上榜原因拆买卖营业部）
python 开发产物/scripts/render.py --stock 002354.SZ --range   # 个股区间统计
python 开发产物/scripts/render_html.py --out lhb.html         # 交互式 HTML 看板（搜索/筛选/排序/展开详情）
python 开发产物/scripts/render_html.py --stock 002354.SZ --out r.html  # 个股区间统计 HTML
python 开发产物/scripts/seat_tags.py                          # 自检席位标签库
```

## 席位标签库（核心资产）
- 北向 / 机构：确定性关键词，零歧义。
- 游资 / 量化：`scripts/seat_tags.py` 的 `SEAT_LIBRARY` 种子库（中信溧阳路、宁波桑田路、
  东财拉萨系、欢乐海岸、成都系…）。
- 外部覆盖：`export B7_SEAT_OVERRIDE=/path/seats.json`，格式 `[{"match","category","tag","note"}]`。
- ⚠️ 席位—游资对应会随时间变动，**需要你持续喂新席位**才越用越准；仅供研究参考，不构成指认或投资建议。

## 输出在哪
- 结果落地：`生产产物/database.parquet`（个股行 `result_type=lhb_stock` + 每日 1 行汇总 `lhb_summary`）
- 看板样例：`生产产物/sample_lhb.html`

## 目录
```
build-b7-lhb-monitor/
├── 开发产物/  SKILL.md · skill.json · references/api_guide.md ·
│              scripts/{build,seat_tags,render,render_html,test}.py
└── 生产产物/  SKILL.md · database.parquet
```

详细字段口径见 [开发产物/SKILL.md](开发产物/SKILL.md) 与 [开发产物/references/api_guide.md](开发产物/references/api_guide.md)。
