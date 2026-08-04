"""The Harness CLI (CLAUDE.md §14, §6.2.4).

`harness preflight` is a standalone deliverable, not a step on the way to a run
(§6.2.4): it answers "can this even be connected to, and what is missing" before
anyone commits to more. So it takes no arming, produces the Preflight Report on
its own, and exits non-zero when the verdict is `blocked` — the exit code is what
makes it usable from a client's own scheduler without parsing prose.

**No flag here can change a verdict.** There is no `--force`, no `--skip`, and no
bulk acknowledgement: §6.2.3 rule 4 says warnings are acknowledged individually
and by name, because "acknowledge all" is the same thing as not reading them.
Acknowledgement itself belongs to arming (BUILD-PLAN item 6); what this command
does is print each warning's `check_id`, which is the name that will be
acknowledged there. `tests/test_preflight_cli.py` asserts by introspection that
no bypass option has appeared.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer
import yaml
from pydantic import ValidationError
from rich.console import Console

from kernel.stages.preflight import render_report, run_preflight
from kernel.stages.preflight.result import Verdict
from kernel.version import kernel_version
from schemas.manifest import Manifest

app = typer.Typer(
    name="harness",
    help="MAXENG Data Onboarding Harness CLI",
    no_args_is_help=True,
)
console = Console()

#: 0 ready, 1 blocked, 2 the manifest could not be read at all. The third is
#: separate because "your manifest is unreadable" and "your source is not ready"
#: are different problems for whoever is on the other end of the exit code.
EXIT_READY = 0
EXIT_BLOCKED = 1
EXIT_UNUSABLE_MANIFEST = 2


@app.command()
def preflight(
    manifest: Annotated[
        Path,
        typer.Option("--manifest", "-m", help="Path to the engagement manifest (YAML)"),
    ],
) -> None:
    """Verify every §6.2.2 precondition and emit the Preflight Report."""
    try:
        document = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        console.print(f"[bold red]Manifest could not be read:[/bold red] {exc}")
        raise typer.Exit(EXIT_UNUSABLE_MANIFEST) from exc

    try:
        parsed = Manifest.model_validate(document)
    except ValidationError as exc:
        # A manifest that will not load is the most legible blocker there is,
        # and reporting it here is what keeps §6.2.2's governance blockers
        # visible even when `schemas/manifest.py` refuses them first (§4.2.6).
        console.print("[bold red]PREFLIGHT — BLOCKED[/bold red]")
        console.print("The manifest is not valid, so no check could run:\n")
        console.print(str(exc))
        raise typer.Exit(EXIT_BLOCKED) from exc

    report = run_preflight(
        parsed,
        kernel_version=kernel_version(),
        environment=dict(os.environ),
    )

    console.print(render_report(report))

    raise typer.Exit(EXIT_READY if report.verdict is Verdict.READY else EXIT_BLOCKED)


@app.command()
def arm(
    preflight_digest: Annotated[
        str, typer.Option("--preflight", help="Preflight digest hash")
    ],
    approver: Annotated[str, typer.Option("--approver", help="Approver identity")],
) -> None:
    """Arm a run against a preflight digest. **Not implemented** (BUILD-PLAN item 6)."""
    console.print(
        "[bold red]arm is not implemented.[/bold red] Arming resolves identity "
        "against the client's IdP (§6.2.3) and nothing here does that yet; a "
        "command that printed a success line would be a gate that looks armed "
        "and authorises nothing."
    )
    _ = (preflight_digest, approver)
    raise typer.Exit(EXIT_UNUSABLE_MANIFEST)


if __name__ == "__main__":
    app()
