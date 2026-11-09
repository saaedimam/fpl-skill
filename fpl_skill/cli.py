import os
import sys
import click
from fpl_skill.account_adapter import FPLAccountAdapter
from fpl_skill.backtest import CaptainBacktest, BenchBacktest, TransferBacktest
from fpl_skill.current_data import CurrentDataError

CURRENT_DATA_EXIT = 3


def _gate_failure(exc):
    """Release gate: surface current-data failures loudly with a distinct exit code."""
    click.echo(f"⛔  CURRENT-DATA GATE FAILED: {exc}", err=True)
    click.echo("No recommendation produced. Refresh live FPL data or pick an upcoming gameweek.", err=True)
    sys.exit(CURRENT_DATA_EXIT)


@click.group()
def cli():
    """FPL Skill CLI."""


@cli.command()
def verify():
    """Display FPL account verification status."""
    team_id = os.environ.get("FPL_TEAM_ID")
    if not team_id:
        click.echo("Error: FPL_TEAM_ID not set.")
        sys.exit(1)
    adapter = FPLAccountAdapter(team_id)
    active_gw = adapter.get_active_event_id()
    state = adapter.get_state(active_gw)
    ownership = state.get("ownership_state", "UNAVAILABLE")
    opt_state = state.get("optimization_state", "OPTIMIZATION_BLOCKED")

    click.echo("FPL ACCOUNT\n-----------")
    click.echo(f"Team ID: {team_id}")
    click.echo(f"Active GW: {active_gw}")
    click.echo(f"Ownership State: {ownership}")
    click.echo(f"Optimization State: {opt_state}")

    if ownership == "VERIFIED_CURRENT":
        click.echo("Identity: VERIFIED")
        click.echo("Auth: VALID (Authenticated Session)")
    elif ownership == "PUBLISHED_EVENT_PICKS":
        click.echo("Identity: PUBLIC_ENTRY")
        click.echo("Auth: UNAUTHENTICATED (Published Event Picks)")
    elif ownership == "HISTORICAL_FALLBACK":
        click.echo("Identity: PUBLIC_ENTRY")
        click.echo("Auth: UNAUTHENTICATED (Historical Fallback)")
    else:
        click.echo("Identity: UNVERIFIED")
        click.echo("Auth: UNAVAILABLE")


@cli.command()
@click.option('--gw', type=int, default=None, help='Scope to specific gameweek (optional)')
@click.option('--by-category', is_flag=True, help='Break down bias per category')
def calibrate(gw, by_category):
    """
    Display forecast calibration metrics and bias detection.

    States:
    - NO_TRACK_RECORD_YET: Fresh season, no completed GW results
    - INSUFFICIENT_SAMPLE: Need 6 completed GWs or 20 player-forecast pairs
    - READY: Metrics available (MAE, RMSE, Brier, log_loss, etc.)
    """
    from fpl_skill.forecast_scorecard import ForecastScorecard

    scorecard = ForecastScorecard.load()
    metrics = scorecard.compute_metrics(gw=gw, by_category=by_category)

    if metrics["status"] == "NO_TRACK_RECORD_YET":
        click.echo("ℹ️  No track record yet — season is fresh.")
        click.echo(f"   Reason: {metrics['reason']}")
        click.echo("   First record available after GW1 results are finalized.")
        return

    if metrics["status"] == "INSUFFICIENT_SAMPLE":
        click.echo("⚠️  Insufficient sample — cannot determine bias yet.")
        click.echo(f"   {metrics['reason']}")
        return

    # READY state
    click.echo("📊 Forecast Scorecard — Metrics")
    scope_str = f" (GW {gw})" if gw else ""
    click.echo(f"   Sample size: {metrics['sample_size']} records, {metrics['completed_gameweeks']} completed GWs{scope_str}")
    click.echo()
    click.echo("Expected Points (continuous):")
    click.echo(f"  • MAE (Mean Absolute Error):  {metrics['mae']}")
    click.echo(f"  • RMSE (Root Mean Squared):   {metrics['rmse']}")
    click.echo(f"  • Signed Bias:                {metrics['signed_bias']}")

    if metrics.get('brier'):
        click.echo()
        click.echo("Probability Forecasts:")
        click.echo(f"  • Brier Score: {metrics['brier']}")

    if metrics.get('log_loss'):
        click.echo()
        click.echo(f"  • Log Loss:    {metrics['log_loss']}")

    if by_category and metrics.get("by_category"):
        click.echo()
        click.echo("Bias by Category:")
        for cat, cat_m in metrics["by_category"].items():
            click.echo(f"  • {cat} (N={cat_m['count']}): MAE={cat_m['mae']}, Bias={cat_m['signed_bias']}")

    click.echo()
    click.echo("✅ Calibration data available. Use `/predict <player> <horizon>` for live forecasts.")


@cli.command()
@click.option("--gw", default=None, type=int, help="Target gameweek for the decision snapshot.")
def backtest_captain(gw):
    """Backtest captain recommendations against actual outcomes."""
    team_id = os.environ.get("FPL_TEAM_ID")
    if not team_id:
        click.echo("Error: FPL_TEAM_ID not set.")
        sys.exit(1)
    try:
        bt = CaptainBacktest(team_id)
        state = bt.adapter.get_state(gw or bt.adapter.get_active_event_id())
        if state["optimization_state"] != "OPTIMIZATION_READY":
            click.echo(f"⛔  State not ready: {state['optimization_state']}")
            sys.exit(1)
        target_gw = gw or state["target_gameweek"]
        dec = bt.record_decision(target_gw, state["squad_ids"])
        click.echo("CAPTAIN RECOMMENDATION\n----------------------")
        click.echo(f"GW{target_gw} Captain : {dec.recommended_captain_name}")
        click.echo(f"GW{target_gw} Vice    : {dec.recommended_vice_name}")
        click.echo()
        click.echo("ℹ️  Backtest certificate generated after GW results are final.")
        click.echo("    Run `/backtest-captain --gw <N>` with actuals to calibrate.")
    except CurrentDataError as e:
        _gate_failure(e)
    except Exception as e:
        click.echo(f"Error: {e}")
        sys.exit(1)


@cli.command()
@click.option("--gw", default=None, type=int, help="Target gameweek for the decision snapshot.")
def backtest_bench(gw):
    """Backtest bench-order recommendations against actual minutes."""
    team_id = os.environ.get("FPL_TEAM_ID")
    if not team_id:
        click.echo("Error: FPL_TEAM_ID not set.")
        sys.exit(1)
    try:
        bt = BenchBacktest(team_id)
        state = bt.adapter.get_state(gw or bt.adapter.get_active_event_id())
        if state["optimization_state"] != "OPTIMIZATION_READY":
            click.echo(f"⛔  State not ready: {state['optimization_state']}")
            sys.exit(1)
        target_gw = gw or state["target_gameweek"]
        dec = bt.record_decision(target_gw, state["squad_ids"])
        click.echo("BENCH ORDER\n-----------")
        for rank, pid in enumerate(dec.bench_order):
            p = bt.elements.get(pid, {})
            click.echo(f"  Sub {rank + 1}: {p.get('web_name', pid)}")
        click.echo()
        click.echo("ℹ️  Backtest certificate generated after GW results are final.")
    except CurrentDataError as e:
        _gate_failure(e)
    except Exception as e:
        click.echo(f"Error: {e}")
        sys.exit(1)


@cli.command()
@click.option("--gw", default=None, type=int, help="Target gameweek for the decision snapshot.")
@click.option("--bank", default=0.0, type=float, help="Bank in £m (e.g. 0.5).")
def backtest_transfer(gw, bank):
    """Backtest 1-FT transfer recommendations against actual EP gains."""
    team_id = os.environ.get("FPL_TEAM_ID")
    if not team_id:
        click.echo("Error: FPL_TEAM_ID not set.")
        sys.exit(1)
    try:
        bt = TransferBacktest(team_id)
        state = bt.adapter.get_state(gw or bt.adapter.get_active_event_id())
        if state["optimization_state"] != "OPTIMIZATION_READY":
            click.echo(f"⛔  State not ready: {state['optimization_state']}")
            sys.exit(1)
        target_gw = gw or state["target_gameweek"]
        dec = bt.record_decision(target_gw, state["squad_ids"], bank=bank)
        if dec is None:
            click.echo("ℹ️  No transfer improves EP by the 1-point threshold. Hold.")
            return
        click.echo("TRANSFER RECOMMENDATION\n-----------------------")
        click.echo(f"OUT : {dec.player_out_name}")
        click.echo(f"IN  : {dec.player_in_name}")
        click.echo(f"Projected EP gain (GW3–6): +{dec.ep_gain_projected:.2f}")
        click.echo()
        click.echo("ℹ️  Backtest certificate generated after GW results are final.")
    except CurrentDataError as e:
        _gate_failure(e)
    except Exception as e:
        click.echo(f"Error: {e}")
        sys.exit(1)


@cli.command()
@click.option("--gw", default=None, type=int, help="Upcoming gameweek (default: live next event).")
@click.option("--squad-ids", default=None, help="Comma-separated 15 element ids (read-only; skips account state).")
def predict(gw, squad_ids):
    """Read-only XI/captain projection for an upcoming gameweek (current-data gated)."""
    import json as _json
    from fpl_skill.prediction_engine import PredictionEngine
    from fpl_skill.current_data import next_gameweek
    team_id = os.environ.get("FPL_TEAM_ID")
    if not team_id and not squad_ids:
        click.echo("Error: set FPL_TEAM_ID or pass --squad-ids.")
        sys.exit(1)
    try:
        engine = PredictionEngine(team_id or "0")
        target = gw or next_gameweek(engine.events)
        squad = None
        if squad_ids:
            ids = [int(x) for x in squad_ids.split(",") if x.strip()]
            missing = [i for i in ids if i not in engine.elements]
            if missing:
                raise CurrentDataError(f"Unknown element ids in current bootstrap: {missing}")
            squad = [engine.elements[i] for i in ids]
        res = engine.run(target, squad=squad)
    except CurrentDataError as e:
        _gate_failure(e)
    if res.get("status") == "BLOCKED":
        click.echo(f"⛔  BLOCKED: {res.get('reason')}")
        sys.exit(2)
    click.echo(_json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    cli()
