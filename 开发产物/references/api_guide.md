# B7 龙虎榜监控+席位标签库 —— 数据接口与字段说明

## 数据来源

正式生产使用 PandaData（`panda_data` ≥ 0.0.9，默认网关 `http://pandadata.pandaaiquant.com`）。

| 接口 | 用途 | B7 中的角色 | 实测速度（PandaData_实战使用经验.md） |
|---|---|---|---|
| `get_lhb_list` | 龙虎榜异动股列表 | 上榜标的、上榜原因(type)、金额、涨跌幅、换手 | 一月 ~0.8s |
| `get_lhb_detail` | 龙虎榜买/卖席位明细（`side=buy/sell/cum`，可全市场 `symbol=None`） | 席位标签匹配、机构/游资/北向净额 | 一周全市场 ~0.8s（1500+ 行） |
| `get_stock_detail` | 股票基础信息 | 股票名 | <0.1s |
| `get_trade_cal` | 交易日历 | backfill 逐日 | 0.1s |

不得使用来源不明、字段不稳定、手工整理的临时表作为正式输入。
参考项目 `skills_dev/.../capital_pricing/seat_analysis` 仅借鉴四类席位分类逻辑，**数据一律以 PandaData 实际返回为准**。

## 凭证（环境变量）

```bash
export PANDA_USERNAME=<86开头手机号>      # 兼容 PANDA_DATA_USERNAME
export PANDA_PASSWORD=<密码>              # 兼容 PANDA_DATA_PASSWORD
# 可选：export PANDA_BASE_URL=...         # 覆盖默认网关
# 可选：export B7_SEAT_OVERRIDE=/path/seats.json   # 席位标签外部覆盖
```

## 接口字段口径

### get_lhb_list（异动股）

| 字段 | 含义 |
|---|---|
| symbol / date | 标的 / 龙虎榜日期 |
| type | 上榜类型代码（`G0007`=日涨幅偏离7%≈涨停，`T0020`=日换手率20% 等） |
| reason | 上榜原因文字 |
| amount / change_rate / turnover / deviation | 龙虎榜金额 / 涨跌幅 / 换手 / 偏离值 |

> 一只票一天可能多条上榜原因 → B7 按 `(symbol,date)` 合并 reason，取 amount 最大。

### get_lhb_detail（席位明细）

| 字段 | 含义 |
|---|---|
| symbol / date / side | 标的 / 日期 / 买卖方向（buy/sell/cum） |
| rank | 龙虎榜排名 |
| agency | 营业部名称（**席位标签匹配的输入**） |
| b_value / s_value | 买入 / 卖出金额 |
| reason | 上榜原因 |

## 席位标签库口径（`seat_tags.py`）

```text
匹配优先级：北向 > 机构 > 种子库(游资/量化) > 营业部 > 普通
北向：agency 含 "沪股通专用"/"深股通专用"/...
机构：agency 含 "机构专用"
游资/量化：seat_library.json 子串匹配（最长子串优先），外部 B7_SEAT_OVERRIDE 优先于内置
营业部：库未命中但含 "营业部/分公司/证券总部/自营" 的具名券商席位
        （能进买卖前五即显著资金，归营业部而非普通，避免游资盘漏统计；实测覆盖率≈99%）
普通：无法识别的异常名（极少）

席位库（两层，匹配优先级：北向>机构>外部覆盖>爬取精确映射>子串种子库>营业部兜底>普通）：

seat_yyb_map.json（最高优先级，营业部全称精确匹配）：由爬取的「游资席位标签集锦」CSV 经
  build_seat_map.py 生成，317 营业部 → {category, tag, alias(游资本尊:章盟主/作手新一/消闲派…),
  group(标签类型), confidence(A-高/B-中/C-低), last_seen}。一营业部多标签时取最优(有效>置信度>观测次数)。
  标签类型含"量化"(三板组/量化打板/量化基金等策略量化集群)→category=量化；其余→游资。
  重爬刷新：新 CSV 放 references/seat_data/ → python scripts/build_seat_map.py。
  ⚠️ 游资别名是民间观测映射(非券商官方身份)，会迁移，结合 confidence/last_seen 用。

seat_library.json（子串种子库兜底，独立可维护，改 JSON 即扩库，不动代码）：
  rules: {north, inst, branch} 确定性关键词
  seats: [{match, category, tag(俗称), group(帮派), tier(一线/二线), alias(游资本尊·默认空), note}]
  帮派(group)：上海帮/深圳帮/宁波系/浙系/成都系/佛山系/拉萨系/温州帮/北京帮/量化通道/外资通道
  alias 槽位留给使用方核实后填本尊名号；本库不臆造民间传闻，亦可用 B7_SEAT_OVERRIDE 临时覆盖

游资盘净买 hotmoney_net = Σ(游资 + 营业部 的 b−s)   # 非机构/非北向/非量化的活跃资金
known_seat_cnt = 知名游资席位数（高亮）; desk_seat_cnt = 游资盘席位数
外资量化通道(高盛/摩根/中金/中信上海分公司/瑞银/野村…)归"量化"，不计入游资盘
```

种子库为公开游资复盘圈广为流传的活跃席位整理（中信溧阳路、宁波桑田路、东财拉萨系、欢乐海岸…），
仅供研究参考，**会随时间变动，须持续核对**，不构成对个人/机构的指认或投资建议。

## 个股聚合 + 次日清单口径（`build.py`）

```text
inst_net     = Σ(机构 b_value) - Σ(机构 s_value)
hotmoney_net = Σ(游资 b_value) - Σ(游资 s_value)
north_net    = Σ(北向 b_value) - Σ(北向 s_value)
net_buy      = Σ(全部买方 b_value) - Σ(全部卖方 s_value)

score = 0.35*z(inst_net) + 0.35*z(hotmoney_net) + 0.20*z(net_buy) + 0.10*z(known_seat_cnt)
is_watchlist = (rank<=watchlist_top_n) 且 score>=min_score 且 (inst_net>0 或 hotmoney_net>0 或 net_buy>0)
```

权重 / top_n 可经 `run(config=...)` / `maintain_daily(cfg=...)` 覆盖（见 `DEFAULT_CONFIG`）。

## 多上榜原因拆分 + 区间统计（v1.1）

### 按上榜原因拆分（`reasons`）

一只票一天可有多条上榜原因（`get_lhb_detail` 的 `type` 字段，如 G0007 涨幅偏离 + T0020 换手），
每条原因对应各自一组买入/卖出营业部。`build_pool` 保留 `type` 并按其分组：

```text
result_json.reasons = [
  {type, reason, buy:[{agency,category,tag,b,s,rank}], sell:[...], buy_total, sell_total}, ...
]   # 按 buy_total 降序；对应个股龙虎榜详情页
result_json.buy_seats / sell_seats = 跨原因聚合后的席位列表（每席位带 b/s）
n_reasons = 上榜原因条数
```

> 注：`net_buy` = Σ(买方席位 b) − Σ(卖方席位 s)，即 PandaData 返回的龙虎榜上榜席位(通常买卖各 top5)净额。
> 与部分行情软件"今日净买入"口径可能不同（后者可能含非 top5 成交），本工具以接口返回席位为准。

### 区间统计（`range_stats`）

```text
range_stats(panel, ts_code, start, end)：
  从已落地 parquet 历史读该票区间内每日 result_json，
  按营业部聚合 总买(Σb) / 总卖(Σs) / 净额 / 上榜次数，按净额降序。
```

依赖已 `save_parquet` 的历史；区间统计前需先 `backfill` 或多日 `maintain_daily` 积累。

## 流量管理

- 龙虎榜是事件型，单日数据小（列表 + 买 + 卖 三次请求，~秒级），每日维护极省流量。
- backfill 逐交易日抓取；遇配额/服务异常（`500009`/`200103`/`ServiceError`/`504`）中断并提示。
- 错误码：`500009` 单日流量超限（等 0:00 重置）；`200103` 权限不足；`504` 网关超时（重试）。

## 异常处理

- 输入为空 / 缺 `ts_code`+`agency` → 抛明确 `ValueError`。
- 当日无龙虎榜 → 返回空表（事件型，正常现象）。
- 股票名 / 单个接口失败 → 优雅降级，名称留空，主流程不中断。
- `result_json` 必须为合法 JSON（`check_quality` 校验）。
