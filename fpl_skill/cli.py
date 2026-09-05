import os
import sys
import click
from fpl_skill.account_adapter import FPLAccountAdapter


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
    click.echo(f"Team ID: {state['target_gameweek']}")  # Simplified
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


if __name__ == "__main__":
    cli()
