import typer
from rich.console import Console

app = typer.Typer(
    name="harness",
    help="MAXENG Data Onboarding Harness CLI",
    no_args_is_help=True,
)
console = Console()


@app.command()
def preflight(
    manifest: str = typer.Option(
        ..., "--manifest", "-m", help="Path to manifest YAML"
    ),
):
    """Run preflight readiness checks against bound source."""
    console.print(
        f"[bold green]Running preflight for manifest:[/bold green] {manifest}"
    )


@app.command()
def arm(
    preflight_digest: str = typer.Option(..., "--preflight", help="Preflight digest hash"),
    approver: str = typer.Option(..., "--approver", help="Approver identity"),
):
    """Arm the execution run with explicit approval."""
    console.print(
        f"[bold yellow]Arming run with digest:[/bold yellow] {preflight_digest} by {approver}"
    )


if __name__ == "__main__":
    app()