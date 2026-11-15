from typer.testing import CliRunner

from supportkit.cli import app


def test_help_lists_commands():
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("seed", "serve", "eval", "migrate", "db-status"):
        assert cmd in result.output
