import sys

import pytest

from boussole.boussole import PRHandler, main  # Import main and PRHandler


def main_args(trigger_comment):
    return [
        "prog",
        "--github-token",
        "token",
        "--pr-num",
        "1",
        "--pr-sender",
        "user",
        "--comment-sender",
        "admin",
        "--repo-owner",
        "owner",
        "--repo-name",
        "repo",
        "--trigger-comment",
        trigger_comment,
        "--lgtm-threshold",
        "1",
        "--lgtm-permissions",
        "admin,write",
        "--lgtm-review-event",
        "APPROVE",
        "--merge-method",
        "squash",
    ]


# Dummy response to simulate successful API call.
class DummyResponse:
    """
    Dummy response object to simulate successful API call.
    """

    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text

    def getcode(self):
        return self.status_code

    def read(self):
        return self.text.encode("utf-8")

    def json(self):
        return {}


# Test for the main function with a valid "/help" command.
def test_main_help_success(monkeypatch, capsys):
    # Prepare dummy methods to bypass external calls.
    dummy = DummyResponse(200, "OK")

    def fake_post_comment(_, msg):
        # Verify that HELP_TEXT is being passed.
        assert "help" in msg.lower()
        return dummy

    monkeypatch.setattr(PRHandler, "_post_comment", fake_post_comment)
    monkeypatch.setattr(PRHandler, "check_status", lambda self, *_: True)
    monkeypatch.setattr(PRHandler, "check_response", lambda self, resp: True)

    # Set sys.argv with valid parameters and a trigger comment for "help".
    sys.argv = main_args("/help")

    # Call main; expecting it to complete without sys.exit
    try:
        main()
    except SystemExit as e:
        pytest.fail(f"main() exited unexpectedly with code {e.code}")

    captured = capsys.readouterr().out
    # Optionally verify that some output was produced
    assert "help" in captured.lower() or captured == ""


# Test for the main function with an invalid command.
def test_main_invalid_command(monkeypatch):
    # Set sys.argv with a trigger comment that does not match a valid command.
    sys.argv = main_args("/invalidcmd")
    # Monkey-patch sys.exit to capture the exit code.
    exit_code = None

    def fake_exit(code):
        nonlocal exit_code
        exit_code = code
        raise SystemExit(code)

    monkeypatch.setattr(sys, "exit", fake_exit)

    with pytest.raises(SystemExit):
        main()
    assert exit_code == 1


@pytest.mark.parametrize(
    ("trigger_comment", "expected"),
    [
        ("/help merge", "Syntax:"),
        ("/help /lgtm", "Self-approval is rejected"),
    ],
)
def test_main_command_specific_help(monkeypatch, trigger_comment, expected):
    dummy = DummyResponse(200, "OK")

    def fake_post_comment(_, message):
        assert expected in message
        assert "Permissions:" in message
        assert "Side effects:" in message
        return dummy

    monkeypatch.setattr(PRHandler, "_post_comment", fake_post_comment)
    monkeypatch.setattr(PRHandler, "check_status", lambda self, *_: True)
    monkeypatch.setattr(PRHandler, "check_response", lambda self, resp: True)
    sys.argv = main_args(trigger_comment)

    main()


@pytest.mark.parametrize("trigger_comment", ["/help frobnicate", "/help merge now"])
def test_main_unknown_help_topic(monkeypatch, trigger_comment):
    dummy = DummyResponse(200, "OK")

    def fake_post_comment(_, message):
        assert "Unknown Help Topic" in message
        assert "Available Commands" in message
        return dummy

    monkeypatch.setattr(PRHandler, "_post_comment", fake_post_comment)
    monkeypatch.setattr(PRHandler, "check_status", lambda self, *_: True)
    monkeypatch.setattr(PRHandler, "check_response", lambda self, resp: True)
    sys.argv = main_args(trigger_comment)

    main()
