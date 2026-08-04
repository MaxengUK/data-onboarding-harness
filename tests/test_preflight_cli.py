"""`harness preflight` as a standalone deliverable (CLAUDE.md §6.2.4, §6.2.3).

The exit code is the deliverable's real interface: §6.2.4 sells preflight as the
cheapest first contact with a client's data, and that only works if a client's
own scheduler can act on the result without parsing prose.

The other property here is negative and matters more — **no option on this
command can change a verdict.** §0 forbids a `--force` or `--skip-checks` on
blockers, and §6.2.3 rule 4 forbids a bulk acknowledgement, because "acknowledge
all" is the same thing as not reading them. Both are asserted by introspecting
the command's parameters, so adding one is a red build rather than a diff nobody
reads.
"""

from __future__ import annotations

import yaml
from typer.testing import CliRunner

from kernel.cli import EXIT_BLOCKED, EXIT_UNUSABLE_MANIFEST, app
from tests.conftest import MINIMAL_MANIFEST

runner = CliRunner()

FORBIDDEN_OPTION_TOKENS = (
    "force",
    "skip",
    "override",
    "acknowledge",
    "ack",
    "ignore",
    "bypass",
    "yes",
    "all",
)


def write_manifest(tmp_path, document: dict):
    path = tmp_path / "manifest.yaml"
    path.write_text(yaml.safe_dump(document, allow_unicode=True), encoding="utf-8")
    return path


def test_a_blocked_verdict_exits_non_zero(tmp_path, source_dir, environment) -> None:
    path = write_manifest(tmp_path, MINIMAL_MANIFEST)

    result = runner.invoke(app, ["preflight", "--manifest", str(path)], env=environment)

    assert result.exit_code == EXIT_BLOCKED
    assert "BLOCKED" in result.stdout


def test_an_unreadable_manifest_exits_differently_from_a_blocked_one(tmp_path) -> None:
    """"Your manifest is broken" and "your source is not ready" are different
    problems for whoever is reading the exit code."""
    missing = tmp_path / "absent.yaml"

    result = runner.invoke(app, ["preflight", "--manifest", str(missing)])

    assert result.exit_code == EXIT_UNUSABLE_MANIFEST


def test_an_invalid_manifest_is_reported_as_blocked_not_as_a_crash(tmp_path) -> None:
    """§4.2.6's retention floor is refused by the loader, and §6.2.2 still lists
    it as a governance blocker. Reporting the load failure is what keeps it
    visible rather than a stack trace."""
    inverted = {
        **MINIMAL_MANIFEST,
        "audit": {"location": "/srv/harness/audit", "retention_days": 30},
    }
    path = write_manifest(tmp_path, inverted)

    result = runner.invoke(app, ["preflight", "--manifest", str(path)])

    assert result.exit_code == EXIT_BLOCKED
    assert "BLOCKED" in result.stdout


def test_arm_refuses_rather_than_printing_a_success_line(tmp_path) -> None:
    """A gate that looks armed and authorises nothing is worse than an absent
    command (BUILD-PLAN item 6)."""
    result = runner.invoke(app, ["arm", "--preflight", "abc", "--approver", "someone"])

    assert result.exit_code != 0
    assert "not implemented" in result.stdout


def test_no_command_offers_a_way_past_a_blocker() -> None:
    from typer.main import get_command

    command = get_command(app)
    for name, sub in command.commands.items():  # type: ignore[attr-defined]
        for parameter in sub.params:
            # `param_type_name` rather than an isinstance against click.Option:
            # click is a transitive dependency here, not a declared one, and a
            # test that guards a §0 rule should not be the thing that breaks
            # when it moves.
            if getattr(parameter, "param_type_name", "") != "option":
                continue
            for opt in parameter.opts:
                # Segment match, not substring: `--install-completion` contains
                # "all" and is not a bypass. A real one would be `--force` or
                # `--acknowledge-all`, and both are caught as whole segments.
                segments = opt.lstrip("-").lower().split("-")
                offending = sorted(set(segments) & set(FORBIDDEN_OPTION_TOKENS))

                assert not offending, (
                    f"`harness {name} {opt}` would let a caller past a blocker or "
                    f"acknowledge warnings in bulk (§0, §6.2.3 rule 4)"
                )


def test_preflight_needs_no_arming_to_run(tmp_path, source_dir, environment) -> None:
    """§6.2.4: it runs standalone, which is what makes it a first-contact
    deliverable rather than a step inside a run.

    Asserted as "the command takes no arming input and still produced a digest",
    not as a string absent from the output — the output legitimately mentions
    approval-adjacent words, and an assertion over prose would break on wording.
    """
    from typer.main import get_command

    preflight_command = get_command(app).commands["preflight"]  # type: ignore[attr-defined]
    option_names = {
        opt
        for parameter in preflight_command.params
        if getattr(parameter, "param_type_name", "") == "option"
        for opt in parameter.opts
    }

    assert not any("arm" in opt or "approv" in opt or "token" in opt for opt in option_names)

    path = write_manifest(tmp_path, MINIMAL_MANIFEST)
    result = runner.invoke(app, ["preflight", "--manifest", str(path)], env=environment)

    assert "DIGEST" in result.stdout
