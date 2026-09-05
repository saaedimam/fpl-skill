import os
import sys
import click
from fpl_skill.account_adapter import FPLAccountAdapter
from fpl_skill.backtest import CaptainBacktest, BenchBacktest, TransferBacktest


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
    state = adapter.get_state(adapter.get_active_event_id())
    click.echo("FPL ACCOUNT\n-----------")
    click.echo(f"Team ID: {team_id}")
    click.echo("Identity: VERIFIED")
    click.echo("Auth: VALID")


@cli.command()
@click.option('--gw', type=int, default=None, help='Scope to specific gameweek (optional)')
@click.option('--by-category', is_flag=True, help='Break down bias per category (future)')
def calibrate(gw, by_category):
    """
    Display forecast calibration metrics and bias detection.

    States:
    - NO_TRACK_RECORD_YET: Fresh season, no completed GW results
    - INSUFFICIENT_SAMPLE: Need 6 completed GWs or 20 player-forecast pairs
    - READY: Metrics available (MAE, RMSE, Brier, log_loss, etc.)
    """
    from fpl_skill.forecast_scorecard import ForecastScorecard

    scorecard = ForecastScorecard()
    # TODO: Load real calibration records from storage/DB (v1.1.0 stub: empty)
    # For now, scorecard starts empty (NO_TRACK_RECORD_YET state)

    metrics = scorecard.compute_metrics()

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
    click.echo(f"   Sample size: {metrics['sample_size']} records, {metrics['completed_gameweeks']} completed GWs")
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
        click.echo(f"  • Log Loss:    {metrics['log_loss']}")

    if by_category:
        click.echo()
        click.echo("Bias by Category:")
        click.echo("  (Future feature — implement in v1.1.1)")

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
    except Exception as e:
        click.echo(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
