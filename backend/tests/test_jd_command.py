import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.parametrize("arguments", [("--pages", "4"), ("--limit", "31")])
def test_jd_poc_command_enforces_hard_limits(arguments: tuple[str, str]) -> None:
    with pytest.raises(CommandError):
        call_command("jd_poc", "--target-id", "1", *arguments)
