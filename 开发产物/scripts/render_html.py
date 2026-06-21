#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BUILD-B7 龙虎榜 —— 交互式单文件 HTML 看板
================================================================
自包含（无外部依赖），内嵌当日数据 + 原生 JS，支持：
  - Tab 切换：股票 / 机构合集 / 营业部合集 / 次日关注
  - 搜索框（名称/代码）+ 筛选 chips（次日关注/机构净买/游资净买/北向净买）
  - 列排序（净买入 / 机构净买 / 游资净买，点表头切换）
  - 点个股行展开「个股详情页」：按上榜原因拆分的买入/卖出营业部表（带席位标签）

另含 render_range_html：某票区间统计（各营业部 总买/总卖/净额）。
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

STOCK_TYPE = "lhb_stock"
SUMMARY_TYPE = "lhb_summary"


def _split_day(panel: pd.DataFrame, date: str | None):
    panel = panel.copy()
    panel["trade_date"] = panel["trade_date"].astype(str)
    day = date or (panel["trade_date"].max() if not panel.empty else "")
    if day:
        day = pd.to_datetime(day).strftime("%Y-%m-%d")
    d = panel[panel["trade_date"] == day]
    stocks = d[d["result_type"] == STOCK_TYPE].copy()
    srow = d[d["result_type"] == SUMMARY_TYPE]
    summary = json.loads(srow.iloc[0]["result_json"]) if len(srow) else {}
    return stocks, summary, day


def _payload(stocks: pd.DataFrame) -> list:
    out = []
    for _, r in stocks.iterrows():
        j = json.loads(r["result_json"])
        out.append({
            "code": r["ts_code"], "name": r["name"] or r["ts_code"], "board": r["board_type"],
            "net": j.get("net_buy", 0), "inst": j.get("inst_net", 0), "hot": j.get("hotmoney_net", 0),
            "north": j.get("north_net", 0), "quant": j.get("quant_net", 0),
            "wl": bool(j.get("is_watchlist")), "rank": j.get("watchlist_rank", 0),
            "reason": j.get("reason", ""), "wreason": j.get("watch_reason", ""),
            "nr": j.get("n_reasons", 1), "reasons": j.get("reasons", []),
            "buy_seats": j.get("buy_seats", []),
        })
    return out


_TPL = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>龙虎榜监控 · {day}</title>
<style>
:root{{--bg:#0b0e14;--card:rgba(255,255,255,.04);--line:rgba(255,255,255,.09);--txt:#e6e9ef;
--mut:#8b93a7;--red:#ff5d6c;--gold:#ffce6b;--green:#4fd1a6;--blue:#6ba8ff;--purple:#b794ff;}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(1200px 600px at 70% -10%,#1a1410,#0b0e14);
color:var(--txt);font:14px/1.5 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif;padding:24px}}
h1{{font-size:20px;margin:0 0 2px}}.sub{{color:var(--mut);margin-bottom:16px;font-size:13px}}
.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:18px}}
.kpi{{flex:1;min-width:104px;background:var(--card);border:1px solid var(--line);border-radius:13px;padding:14px 16px}}
.kpi .v{{font-size:22px;font-weight:700}}.kpi .k{{color:var(--mut);font-size:12px;margin-top:2px}}
.bar{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:14px}}
.tabs{{display:flex;gap:6px}}
.tab{{padding:7px 14px;border-radius:10px;border:1px solid var(--line);background:var(--card);
color:var(--mut);cursor:pointer;font-size:13px}}
.tab.on{{background:rgba(255,93,108,.16);border-color:rgba(255,93,108,.4);color:var(--red);font-weight:600}}
input.search{{flex:1;min-width:160px;background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:8px 12px;color:var(--txt);font-size:13px;outline:none}}
.chips{{display:flex;gap:6px;flex-wrap:wrap}}
.chip{{padding:5px 11px;border-radius:9px;border:1px solid var(--line);background:var(--card);
color:var(--mut);cursor:pointer;font-size:12px}}
.chip.on{{background:rgba(107,168,255,.16);border-color:rgba(107,168,255,.4);color:var(--blue)}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
border-radius:13px;overflow:hidden}}
th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:13px;white-space:nowrap}}
th{{color:var(--mut);font-weight:600;background:rgba(255,255,255,.02);cursor:pointer;user-select:none}}
th.sortable::after{{content:" ⇅";opacity:.4;font-size:11px}}
th.asc::after{{content:" ↑";opacity:1}}th.desc::after{{content:" ↓";opacity:1}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}}
.pos{{color:var(--green)}}.neg{{color:var(--red)}}
.code{{color:var(--mut);font-size:11px;margin-left:6px}}
.t-机构,.t-北向{{color:var(--blue)}}.t-游资{{color:var(--gold)}}.t-量化{{color:var(--purple)}}.t-普通{{color:var(--mut)}}
.tg{{display:inline-block;padding:1px 7px;border-radius:7px;font-size:11px;border:1px solid var(--line);margin-right:4px}}
.tg.机构,.tg.北向{{color:var(--blue);border-color:rgba(107,168,255,.4)}}
.tg.游资{{color:var(--gold);border-color:rgba(255,206,107,.4)}}
.tg.量化{{color:var(--purple);border-color:rgba(183,148,255,.4)}}
tr.stock{{cursor:pointer}}tr.stock:hover{{background:rgba(255,255,255,.03)}}
tr.wl td:first-child::before{{content:"★ ";color:var(--gold)}}
.detail{{background:rgba(0,0,0,.18)}}.detail td{{padding:14px 16px}}
.rblock{{margin-bottom:12px}}.rttl{{color:var(--gold);font-weight:600;margin-bottom:6px;font-size:13px}}
.stbl{{width:100%;border:none;background:transparent}}.stbl th,.stbl td{{border-bottom:1px solid var(--line);padding:5px 8px}}
.empty{{color:var(--mut);text-align:center;padding:22px}}
.foot{{color:var(--mut);font-size:11px;margin-top:22px;text-align:center}}
.ladder{{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:12px 14px;margin-bottom:10px}}
.lhd{{display:flex;gap:10px;margin-bottom:8px}}.lhd .bn{{font-weight:700;color:var(--gold)}}.lhd .cnt{{color:var(--mut);font-size:12px}}
.sc{{display:flex;flex-wrap:wrap;gap:6px}}.sc .x{{background:rgba(255,206,107,.12);border:1px solid rgba(255,206,107,.3);
color:var(--gold);border-radius:8px;padding:3px 8px;font-size:12px}}.sc .x em{{font-style:normal;opacity:.6;margin-left:3px}}
</style></head><body>
<h1>🐯 龙虎榜监控 · 席位标签库</h1><div class="sub">{day} ｜ 点个股行展开「上榜原因 → 买卖营业部」详情</div>
<div class="kpis">{kpis}</div>
<div class="bar"><div class="tabs" id="tabs">
  <div class="tab on" data-tab="stock">股票</div><div class="tab" data-tab="inst">机构合集</div>
  <div class="tab" data-tab="seat">营业部合集</div><div class="tab" data-tab="wl">次日关注</div>
</div><input class="search" id="q" placeholder="搜索 名称/代码…"></div>
<div class="chips" id="chips">
  <div class="chip on" data-f="all">全部</div><div class="chip" data-f="wl">次日关注</div>
  <div class="chip" data-f="inst">机构净买</div><div class="chip" data-f="hot">游资净买</div>
  <div class="chip" data-f="north">北向净买</div></div>
<div style="height:12px"></div>
<div id="view"></div>
<div class="foot">BUILD-B7 龙虎榜监控+席位标签库 · 席位标签为可维护种子库 · PandaData 驱动</div>
<script>
const DATA = {data_json};
let tab="stock", filt="all", q="", sortKey="net", sortDir=-1;
const yi=v=>{{const n=Number(v)||0;return (n/1e8).toFixed(2)+"亿";}};
const cls=v=>Number(v)>0?"pos":(Number(v)<0?"neg":"");
const tg=s=>`<span class="tg ${{s.category}}">${{s.category}}${{s.tag?("·"+s.tag):""}}</span>`;
function seatTbl(rows,side){{
  if(!rows||!rows.length) return '<div class="empty">无</div>';
  let h='<table class="stbl"><thead><tr><th>'+(side==="buy"?"买入":"卖出")+'营业部</th><th>标签</th><th style="text-align:right">买入(万)</th><th style="text-align:right">卖出(万)</th></tr></thead><tbody>';
  rows.forEach(s=>{{h+=`<tr><td>${{s.agency}}</td><td>${{s.category!=="普通"?tg(s):""}}</td><td class="num">${{(s.b/1e4).toLocaleString(undefined,{{maximumFractionDigits:0}})}}</td><td class="num">${{(s.s/1e4).toLocaleString(undefined,{{maximumFractionDigits:0}})}}</td></tr>`;}});
  return h+'</tbody></table>';
}}
function detail(d){{
  let h='<td colspan="7"><div>';
  (d.reasons||[]).forEach(r=>{{
    h+=`<div class="rblock"><div class="rttl">上榜原因：${{r.reason||r.type}}（买${{(r.buy_total/1e4).toLocaleString(undefined,{{maximumFractionDigits:0}})}}万 / 卖${{(r.sell_total/1e4).toLocaleString(undefined,{{maximumFractionDigits:0}})}}万）</div>`;
    h+='<div style="display:flex;gap:14px;flex-wrap:wrap"><div style="flex:1;min-width:280px">'+seatTbl(r.buy,"buy")+'</div><div style="flex:1;min-width:280px">'+seatTbl(r.sell,"sell")+'</div></div></div>';
  }});
  return h+'</div></td>';
}}
function stockRows(){{
  let arr=DATA.stocks.filter(s=>{{
    if(filt==="wl"&&!s.wl)return false;
    if(filt==="inst"&&!(s.inst>0))return false;
    if(filt==="hot"&&!(s.hot>0))return false;
    if(filt==="north"&&!(s.north>0))return false;
    if(q&&!(s.name.includes(q)||s.code.includes(q)))return false;
    return true;}});
  arr.sort((a,b)=>sortDir*((Number(a[sortKey])||0)-(Number(b[sortKey])||0)));
  if(!arr.length)return '<div class="empty">无匹配标的</div>';
  const sh=k=>`class="sortable num ${{sortKey===k?(sortDir<0?'desc':'asc'):''}}" data-k="${{k}}"`;
  let h='<table><thead><tr><th>标的</th><th>板块</th><th>风口/原因</th><th '+sh("net")+'>净买入</th><th '+sh("inst")+'>机构净买</th><th '+sh("hot")+'>游资净买</th><th>原因数</th></tr></thead><tbody>';
  arr.forEach((s,i)=>{{
    h+=`<tr class="stock ${{s.wl?'wl':''}}" data-i="${{DATA.stocks.indexOf(s)}}"><td>${{s.name}}<span class="code">${{s.code}}</span></td><td>${{s.board}}</td><td>${{(s.reason||'').slice(0,16)}}</td><td class="num ${{cls(s.net)}}">${{yi(s.net)}}</td><td class="num ${{cls(s.inst)}}">${{yi(s.inst)}}</td><td class="num ${{cls(s.hot)}}">${{yi(s.hot)}}</td><td class="num">${{s.nr}}</td></tr>`;
  }});
  return h+'</tbody></table>';
}}
function instTab(){{
  let arr=DATA.stocks.filter(s=>s.inst>0&&(!q||s.name.includes(q)||s.code.includes(q))).sort((a,b)=>b.inst-a.inst);
  if(!arr.length)return '<div class="empty">当日无机构净买入。</div>';
  let h='<table><thead><tr><th>标的</th><th>板块</th><th class="num">机构净买</th><th class="num">总净买</th><th>上榜原因</th></tr></thead><tbody>';
  arr.forEach(s=>h+=`<tr class="stock" data-i="${{DATA.stocks.indexOf(s)}}"><td>${{s.name}}<span class="code">${{s.code}}</span></td><td>${{s.board}}</td><td class="num pos">${{yi(s.inst)}}</td><td class="num ${{cls(s.net)}}">${{yi(s.net)}}</td><td>${{(s.reason||'').slice(0,18)}}</td></tr>`);
  return h+'</tbody></table>';
}}
function seatTab(){{
  const m={{}};
  DATA.stocks.forEach(s=>(s.buy_seats||[]).forEach(b=>{{if(b.category!=="游资")return;const k=b.tag||b.agency;(m[k]=m[k]||[]).push({{n:s.name,c:s.code,v:b.b}});}}));
  let keys=Object.keys(m);if(q)keys=keys.filter(k=>k.includes(q)||m[k].some(x=>x.n.includes(q)));
  keys.sort((a,b)=>m[b].length-m[a].length);
  if(!keys.length)return '<div class="empty">当日无命中的知名游资席位。</div>';
  let h='';keys.forEach(k=>{{const ps=m[k].sort((a,b)=>b.v-a.v);
    h+=`<div class="ladder"><div class="lhd"><span class="bn">${{k}}</span><span class="cnt">出手 ${{ps.length}}</span></div><div class="sc">`+
       ps.map(x=>`<span class="x">${{x.n}}<em>${{(x.v/1e8).toFixed(2)}}亿</em></span>`).join('')+'</div></div>';}});
  return h;
}}
function render(){{
  const v=document.getElementById('view');
  document.getElementById('chips').style.display=(tab==="stock")?"flex":"none";
  if(tab==="stock")v.innerHTML=stockRows();
  else if(tab==="inst")v.innerHTML=instTab();
  else if(tab==="seat")v.innerHTML=seatTab();
  else if(tab==="wl"){{const o=filt;filt="wl";v.innerHTML=stockRows();filt=o;}}
  v.querySelectorAll('tr.stock').forEach(tr=>tr.onclick=()=>{{
    const nx=tr.nextElementSibling;
    if(nx&&nx.classList.contains('detail')){{nx.remove();return;}}
    v.querySelectorAll('tr.detail').forEach(e=>e.remove());
    const d=DATA.stocks[+tr.dataset.i];const r=document.createElement('tr');r.className='detail';r.innerHTML=detail(d);tr.after(r);
  }});
  v.querySelectorAll('th.sortable').forEach(th=>th.onclick=()=>{{const k=th.dataset.k;if(sortKey===k)sortDir*=-1;else{{sortKey=k;sortDir=-1;}}render();}});
}}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{{document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));t.classList.add('on');tab=t.dataset.tab;render();}});
document.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{{document.querySelectorAll('.chip').forEach(x=>x.classList.remove('on'));c.classList.add('on');filt=c.dataset.f;render();}});
document.getElementById('q').oninput=e=>{{q=e.target.value.trim();render();}};
render();
</script></body></html>"""


def _kpis_html(d: pd.DataFrame, s: dict) -> str:
    def yi(v):
        try:
            return f"{float(v)/1e8:.2f}亿"
        except Exception:
            return "—"
    kpis = [
        ("上榜", f"{int(s.get('n_lhb', len(d)))}"),
        ("机构买入", f"{int(s.get('n_inst_buy', int((d['inst_net']>0).sum())))}"),
        ("游资活跃", f"{int(s.get('n_hotmoney_buy', int((d['hotmoney_net']>0).sum())))}"),
        ("次日关注", f"{int(s.get('n_watchlist', int(d['is_watchlist'].sum())))}"),
        ("机构净买", yi(s.get('inst_net_total', d['inst_net'].sum()))),
        ("游资净买", yi(s.get('hotmoney_net_total', d['hotmoney_net'].sum()))),
    ]
    return "".join(f'<div class="kpi"><div class="v">{v}</div><div class="k">{k}</div></div>' for k, v in kpis)


def render_html(panel: pd.DataFrame, date: str | None = None) -> str:
    d, s, day = _split_day(panel, date)
    if d.empty:
        return _TPL.format(day=day, kpis="", data_json='{"stocks":[]}')
    payload = {"summary": s, "stocks": _payload(d)}
    return _TPL.format(day=day, kpis=_kpis_html(d, s),
                       data_json=json.dumps(payload, ensure_ascii=False))


# ============================================================
# 区间统计 HTML（某票各营业部 总买/总卖/净额）
# ============================================================
def render_range_html(panel: pd.DataFrame, ts_code: str, start: str | None = None,
                      end: str | None = None) -> str:
    from build import range_stats
    rs = range_stats(panel, ts_code, start, end)
    rows = ""
    for x in rs.get("seats", []):
        tag = f'<span class="tg {x["category"]}">{x["category"]}{("·"+x["tag"]) if x.get("tag") else ""}</span>' \
            if x["category"] != "普通" else ""
        rows += (f'<tr><td>{x["agency"]}</td><td>{tag}</td>'
                 f'<td class="num pos">{x["buy"]/1e4:,.0f}</td>'
                 f'<td class="num neg">{x["sell"]/1e4:,.0f}</td>'
                 f'<td class="num {"pos" if x["net"]>0 else "neg"}">{x["net"]/1e4:,.0f}</td>'
                 f'<td class="num">{x["days"]}</td></tr>')
    if not rows:
        rows = '<tr><td colspan="6" class="empty">区间内无龙虎榜记录</td></tr>'
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>{rs.get('name','')}({ts_code}) 区间统计</title><style>
body{{margin:0;background:#0b0e14;color:#e6e9ef;font:14px/1.5 -apple-system,"PingFang SC",sans-serif;padding:24px}}
h1{{font-size:18px}}.sub{{color:#8b93a7;font-size:13px;margin-bottom:14px}}
table{{width:100%;border-collapse:collapse;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.09);border-radius:13px;overflow:hidden}}
th,td{{padding:9px 12px;text-align:left;border-bottom:1px solid rgba(255,255,255,.09);font-size:13px}}
th{{color:#8b93a7;background:rgba(255,255,255,.02)}}td.num{{text-align:right;font-variant-numeric:tabular-nums}}
.pos{{color:#4fd1a6}}.neg{{color:#ff5d6c}}.empty{{text-align:center;color:#8b93a7;padding:20px}}
.tg{{display:inline-block;padding:1px 7px;border-radius:7px;font-size:11px;border:1px solid rgba(255,255,255,.2)}}
.tg.游资{{color:#ffce6b}}.tg.机构,.tg.北向{{color:#6ba8ff}}.tg.量化{{color:#b794ff}}</style></head><body>
<h1>📊 {rs.get('name','')}({ts_code}) 区间统计</h1>
<div class="sub">{rs.get('start','')} ~ {rs.get('end','')} ｜ {rs.get('n_days',0)} 个上榜日 ｜ 按净额排序</div>
<table><thead><tr><th>营业部</th><th>标签</th><th class="num">总买(万)</th><th class="num">总卖(万)</th>
<th class="num">净额(万)</th><th class="num">上榜次数</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser(description="B7 龙虎榜交互式 HTML 看板")
    ap.add_argument("--parquet", default=str(Path(__file__).resolve().parents[2] / "生产产物" / "database.parquet"))
    ap.add_argument("--date", default=None)
    ap.add_argument("--stock", default=None, help="出某票区间统计 HTML")
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--out", default="lhb_monitor.html")
    args = ap.parse_args()
    panel = pd.read_parquet(args.parquet)
    if args.stock:
        html = render_range_html(panel, args.stock, args.start, args.end)
    else:
        html = render_html(panel, date=args.date)
    Path(args.out).write_text(html, encoding="utf-8")
    print(f"已写出 {args.out}")


if __name__ == "__main__":
    main()
