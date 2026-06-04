import sys

import pytest

from boussole.boussole import PRHandler, main  # Import main and PRHandler


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
    sys.argv = [
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
        "/help",
        "--lgtm-threshold",
        "1",
        "--lgtm-permissions",
        "admin,write",
        "--lgtm-review-event",
        "APPROVE",
        "--merge-method",
        "squash",
    ]

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
    sys.argv = [
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
        "/invalidcmd",
        "--lgtm-threshold",
        "1",
        "--lgtm-permissions",
        "admin,write",
        "--lgtm-review-event",
        "APPROVE",
        "--merge-method",
        "squash",
    ]
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


def test_main_cherry_pick_on_merged_pr(monkeypatch):
    cherry_pick_called = {}

    def fake_check_status(self, num, status):
        return status != "open"

    def fake_get_pr_status(self, num):
        class FakeResp:
            status_code = 200

            def json(self):
                return {"state": "closed", "merged": True}

        return FakeResp()

    def fake_cherry_pick(self, values, immediate=False):
        cherry_pick_called["values"] = values
        cherry_pick_called["immediate"] = immediate

    monkeypatch.setattr(PRHandler, "check_status", fake_check_status)
    monkeypatch.setattr(PRHandler, "_get_pr_status", fake_get_pr_status)
    monkeypatch.setattr(PRHandler, "cherry_pick", fake_cherry_pick)

    sys.argv = [
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
        "/cherry-pick release-1.0",
        "--lgtm-threshold",
        "1",
        "--lgtm-permissions",
        "admin,write",
        "--lgtm-review-event",
        "APPROVE",
        "--merge-method",
        "squash",
    ]

    main()
    assert cherry_pick_called["values"] == ["release-1.0"]
    assert cherry_pick_called["immediate"] is True


def test_main_cherry_pick_on_closed_not_merged_pr(monkeypatch):
    posted_comment = {}

    def fake_check_status(self, num, status):
        return status != "open"

    def fake_get_pr_status(self, num):
        class FakeResp:
            status_code = 200

            def json(self):
                return {"state": "closed", "merged": False}

        return FakeResp()

    def fake_check_membership(self, user):
        return "admin", True

    def fake_post_comment(self, msg):
        posted_comment["msg"] = msg

    monkeypatch.setattr(PRHandler, "check_status", fake_check_status)
    monkeypatch.setattr(PRHandler, "_get_pr_status", fake_get_pr_status)
    monkeypatch.setattr(PRHandler, "_check_membership", fake_check_membership)
    monkeypatch.setattr(PRHandler, "_post_comment", fake_post_comment)

    sys.argv = [
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
        "/cherry-pick release-1.0",
        "--lgtm-threshold",
        "1",
        "--lgtm-permissions",
        "admin,write",
        "--lgtm-review-event",
        "APPROVE",
        "--merge-method",
        "squash",
    ]

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    assert "closed but not merged" in posted_comment["msg"]
