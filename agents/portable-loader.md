# Portable Loader Prompt / 便携加载提示

This file is the portable entrypoint for Hermes, OpenClaw, and any agent runtime that does not
natively discover `SKILL.md` folders. Native runtimes (Claude Code, Codex, Cursor) should read
[SKILL.md](../SKILL.md) directly; the Cursor rule is [cursor-rule.mdc](cursor-rule.mdc) and the
Codex interface is [openai.yaml](openai.yaml).

本文件是 Hermes / OpenClaw 等不原生识别 `SKILL.md` 目录的运行时的便携入口。
把下面这段提示粘贴进运行时的系统提示或工具描述，并把占位路径替换成仓库根目录。

```text
You have access to a local skill named skill-b7-lhb-monitor at:
<SKILL_B7_LHB_MONITOR_ROOT>

Use it when the user wants to pull the post-market A-share dragon-tiger list, tag broker seats as northbound / institution / hot-money / quant / branch, and produce a next-day watchlist or interval statistics.

1. Read <SKILL_B7_LHB_MONITOR_ROOT>/SKILL.md first; it is the canonical declaration.
2. Read <SKILL_B7_LHB_MONITOR_ROOT>/开发产物/SKILL.md for the agent-facing interface (inputs, outputs, run()/validate_input()).
3. Read the references before touching data logic:
   - <SKILL_B7_LHB_MONITOR_ROOT>/开发产物/references/api_guide.md
4. Run entrypoints from <SKILL_B7_LHB_MONITOR_ROOT>:
   python 开发产物/scripts/build.py --mode daily
   python 开发产物/scripts/build.py --mode backfill --start 20250101 --end 20250630
   python 开发产物/scripts/render_html.py
5. Seat tags come from the tag library; hot-money aliases are community observations, not official broker identities, and they migrate over time; output must carry confidence and state that it does not identify any person or institution
6. One-sided days (buyers only or sellers only) must still produce results without raising
7. Reason and interval-statistic definitions follow `开发产物/SKILL.md`; do not invent new aggregation rules
8. Credentials come only from PANDA_USERNAME / PANDA_PASSWORD or ~/.pandadata/pandadata.env; never hard-code or print them.
9. This is a QuantSkills Community Project for research and education only: no investment advice, no return promises, no claim of official endorsement.
```
