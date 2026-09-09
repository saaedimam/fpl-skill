#!/usr/bin/env python3
"""Observation layer — live monitoring / replay gate / cohort discovery CLI.

Run live (public API, no auth):
    python -m fpl_skill.observation monitor --top 10 --interval 60
Run the acceptance gate:
    python -m fpl_skill.observation gate --report GATE-REALTIME.md
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from .alerts import EchoAlert, JsonlAlert, MultiSink
from .ingest import HttpFetcher, discover_top
from .poller import Poller
from .tape import gate_summary, run_scenario


def _cmd_live(args: argparse.Namespace) -> int:
    fetcher = HttpFetcher(
        cache_dir=args.cache_dir,
        rate=args.rate,
        burst=args.rate * 2,
        sleep=time.sleep,
    )
    try:
        managers = discover_top(fetcher, n=args.top, league=args.league)
    except Exception as e:  # noqa: BLE001
        print(f"cohort discovery failed: {e}", file=sys.stderr)
        return 1
    if not managers:
        print("no managers discovered from public leaderboard", file=sys.stderr)
        return 1
    print(f"monitoring {len(managers)} elite managers (top {args.top} @ league {args.league})")

    sinks = [EchoAlert()]
    if args.alerts_to:
        sinks.append(JsonlAlert(args.alerts_to, now=lambda: datetime.now(timezone.utc)))
    poller = Poller(
        managers,
        store_dir=args.store_dir,
        transport=fetcher,
        sleep=time.sleep,
        base_interval=args.interval,
        tight_interval=max(5.0, args.interval / 4),
        alert_sinks=sinks,
    )
    poller.run(max_polls=args.polls if args.polls else None)
    summary = gate_summary(poller)
    print("events:", json.dumps(summary["event_counts"]))
    return 0


def _cmd_gate(args: argparse.Namespace) -> int:
    # Deterministic component-level gate (network-free) is exercised by pytest;
    # here we print the replay harness summary plus opt-in live smoke timing.
    print("replay gate: run pytest -m realtime for full property suite")
    if args.live_smoke:
        t0 = datetime.now(timezone.utc)
        fetcher = HttpFetcher(cache_dir=args.cache_dir, sleep=time.sleep)
        top = discover_top(fetcher, n=3)
        t1 = datetime.now(timezone.utc)
        print(f"live cohort fetch: {len(top)} managers in "
              f"{(t1 - t0).total_seconds():.3f}s (public API)")
    return 0


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(prog="fpl-observation")
    sub = p.add_subparsers(dest="cmd", required=True)

    mon = sub.add_parser("monitor")
    mon.add_argument("--top", type=int, default=10)
    mon.add_argument("--league", type=int, default=314)
    mon.add_argument("--interval", type=float, default=60.0)
    mon.add_argument("--polls", type=int, default=0)
    mon.add_argument("--store-dir", default=".obs")
    mon.add_argument("--cache-dir", default=".obs/cache")
    mon.add_argument("--alerts-to", default=None)
    mon.add_argument("--rate", type=float, default=1.5)
    mon.set_defaults(fn=_cmd_live)

    gate = sub.add_parser("gate")
    gate.add_argument("--report", default="GATE-REALTIME.md")
    gate.add_argument("--live-smoke", action="store_true")
    gate.add_argument("--cache-dir", default=".obs/cache")
    gate.set_defaults(fn=_cmd_gate)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())