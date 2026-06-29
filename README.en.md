# skill-b7-lhb-monitor · Dragon-Tiger Monitor + Seat Tag Library

> **Project status: Community Project.** Created by a community member; **not reviewed, certified, verified, or
> endorsed by QuantSkills**, and not a production-certified project. The `quantskills/` namespace only indicates the
> hosting organization and implies no official status.

> 中文说明见 [README.md](README.md) ｜ Chinese README is the primary version.

A pre-close monitor for the A-share Dragon-Tiger List (龙虎榜). After close it fetches the list, matches branch seats
into North-bound / Institution / Hot-money (游资) / Quant / Branch via a seat-tag library, builds a next-day watchlist,
and produces daily roll-ups (institution set, branch/hot-money set, per-stock detail, interval stats) plus an
interactive HTML dashboard. Data source: **PandaData**.

---

## What it does
Turns raw Dragon-Tiger seat detail into a "tagged capital profile + next-day watchlist + daily roll-up views".

## How to use
- Natural language (after wiring into an agent): "run today's Dragon-Tiger list".
- CLI: `python 开发产物/scripts/build.py --mode daily`, then `render_html.py` for the interactive dashboard.
- Full call rules and field tables: **[开发产物/SKILL.md](开发产物/SKILL.md)**.

## Scenarios
Post-close review agents · hot-money sentiment research · manual review.

## Maintainer
Community member [@ZLHad](https://github.com/ZLHad). Issues / PRs welcome.

## Limitations
- The Dragon-Tiger List is published in the evening; run **after ~19:30**.
- **Seat-to-hot-money aliases are folk observational mappings, NOT official brokerage identities, and migrate over
  time.** Each carries `confidence` (A/B/C) and `last_seen`; C-low must not be treated as a definitive attribution.
  **This library is not an identification of any individual or institution.**
- Depends on a PandaData account and traffic quota.

---

## Quant boundaries (Community Rule §8)
- **Data source**: PandaData (`panda_data` ≥ 0.0.9); `get_lhb_list` / `get_lhb_detail` / `get_stock_detail`.
- **Assumptions**: `net_buy` is the net of the listed seats (top-5 buy/sell), which may differ from some terminals'
  "net buy"; seat classification rules see api_guide.
- **Parameters**: watchlist scoring weights and top-N are configurable.
- **Known limitations**: see "Limitations"; aliases are folk mappings — use with confidence/last_seen.
- **Risk boundary**: output is **objective statistics & capital profiling for research/review**, with no buy/sell advice.
- **Nature**: **research / educational example only**. Not investment advice. No promised returns. No implication
  that any strategy is safe or guaranteed to be profitable.

## Attribution & License (Community Rules §3 / §6)
- License: **GPL-3.0-only** (see [LICENSE](LICENSE)).
- The four-class seat logic is adapted from the local `capital_pricing/seat_analysis`, reimplemented offline and
  reproducibly (no online AI).
- Seat-alias mappings come from the maintainer's crawled/curated observational data (under
  `开发产物/references/seat_data/`), which are **not official brokerage identities** and are for research only.
- Third-party deps: `panda_data`, `pandas`, `numpy`, `pyarrow`, each under their own licenses.
