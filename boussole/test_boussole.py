# pylint: disable=missing-module-docstring,missing-function-docstring,missing-class-docstring,wrong-import-position
import argparse
import sys
from unittest.mock import MagicMock

import pytest

sys.path.append("../boussole")  # TODO: Find a better way to import the module
from boussole.boussole import GitHubAPI, PRHandler  # Import main and PRHandler


class MyFakeResponse:
    def __init__(self, status_code, body):
        self.body = body
        self.status_code = status_code

    def get(self, _key, default=None):
        return self.body if isinstance(self.body, dict) else default

    def json(self):
        return self.body


@pytest.fixture
def mock_api():
    api = GitHubAPI(
        "https://api.github.com/repos/test/repo", {"Authorization": "Bearer test_token"}
    )
    for method in ("get", "post", "put", "delete"):
        setattr(api, method, MagicMock())
    return api


@pytest.fixture
def mock_args():
    return argparse.Namespace(
        pr_num="123",
        pr_sender="test_user",
        comment_sender="reviewer",
        lgtm_threshold=2,
        lgtm_permissions="admin,write",
        lgtm_review_event="APPROVE",
        merge_method="squash",
        repo_owner="test",
        repo_name="repo",
        github_token="test_token",
        trigger_comment="/lgtm",
    )


@pytest.fixture
def pr_handler(mock_api, mock_args):
    return PRHandler(api=mock_api, args=mock_args)


def test_post_comment(pr_handler, mock_api):
    pr_handler._post_comment("Test comment")
    mock_api.post.assert_called_once_with(
        "issues/123/comments", {"body": "Test comment"}
    )


def test_assign_unassign(pr_handler, mock_api):
    pr_handler.assign_unassign("assign", ["user1", "user2"])
    mock_api.post.assert_called_once_with(
        "pulls/123/requested_reviewers", {"reviewers": ["user1", "user2"]}
    )


def test_label(pr_handler, mock_api):
    pr_handler.label(["bug", "enhancement"])

    # Ensure both calls happened
    assert mock_api.post.call_count == 2
    mock_api.post.assert_any_call(
        "issues/123/labels", {"labels": ["bug", "enhancement"]}
    )
    mock_api.post.assert_any_call(
        "issues/123/comments", {"body": "✅ Added labels: <b>bug, enhancement</b>."}
    )


def test_unlabel(pr_handler, mock_api):
    pr_handler.unlabel(["bug"])
    mock_api.delete.assert_called_once_with("issues/123/labels/bug")


def test_check_membership(pr_handler, mock_api):
    mock_api.get.return_value.status_code = 200
    mock_api.get.return_value.json.return_value = {"permission": "write"}
    permission, is_valid = pr_handler._check_membership("reviewer")
    assert permission == "write"
    assert is_valid is True


def test_lgtm(pr_handler, mock_api):
    mock_api.get.return_value.status_code = 200

    # Mock response for PR comments
    def mock_json_comments():
        return [
            {"body": "/lgtm", "user": {"login": "reviewer1"}},
            {"body": "/lgtm", "user": {"login": "reviewer2"}},
        ]

    # Mock response for permissions
    def mock_json_permissions():
        return {"permission": "write"}

    # Assign the side_effect to return different results on multiple calls
    mock_api.get.return_value.json.side_effect = [
        [],
        mock_json_comments(),  # First call to json() -> PR comments
        mock_json_permissions(),  # Second call to json() -> reviewer1 permission
        mock_json_permissions(),  # Third call to json() -> reviewer2 permission
    ]

    assert pr_handler.lgtm() == 2
    mock_api.get.return_value.status_code = 200


def test_lgtm_by_review_request(pr_handler, mock_api, capsys):
    mock_api.get.return_value.status_code = 200

    # Mock response for PR comments with self-approval
    mock_api.get.return_value.json.side_effect = [
        [
            {"state": "APPROVED", "user": {"login": "reviewer1"}},
            {"state": "APPROVED", "user": {"login": "reviewer2"}},
        ],
        [],
        {"permission": "write"},
        {"permission": "write"},
    ]
    pr_handler.lgtm()
    assert "PR approved with LGTM votes" in capsys.readouterr().out


def test_lgtm_self_approval(pr_handler, mock_api):
    mock_api.get.return_value.status_code = 200

    # Mock response for PR comments with self-approval
    mock_api.get.return_value.json.side_effect = [
        [],
        [
            {
                "body": "/lgtm",
                "user": {"login": "test_user"},
                "html_url": "http://test.url",
            },
        ],
    ]

    with pytest.raises(SystemExit) as exc_info:
        pr_handler.lgtm()
    assert exc_info.value.code == 1


def test_lgtm_comments_fetch_error(pr_handler, mock_api):
    mock_api.get.return_value.status_code = 500
    mock_api.get.return_value.text = "API Error"

    with pytest.raises(SystemExit) as exc_info:
        pr_handler.lgtm()
    assert exc_info.value.code == 1


def test_check_membership_invalid_response(pr_handler, mock_api):
    mock_api.get.return_value.status_code = 404
    permission, is_valid = pr_handler._check_membership("nonexistent_user")
    assert permission is None
    assert is_valid is False


def test_merge_pr_no_all_checks_succeed(capsys, pr_handler, mock_api):
    all_checks = MyFakeResponse(
        200,
        {
            "check_runs": [
                {
                    "name": "check-1",
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "http://test.url",
                },
                {
                    "name": "check-2",
                    "status": "completed",
                    "conclusion": "failure",
                    "html_url": "http://test.url",
                },
            ],
        },
    )

    mock_responses = [
        MyFakeResponse(200, {"permission": "admin"}),
        MyFakeResponse(200, {"head": {"sha": "abc123"}}),
        all_checks,
    ]

    mock_api.get.side_effect = mock_responses

    with pytest.raises(SystemExit) as exc_info:
        pr_handler.merge_pr()
        assert "Cannot merge PR" in capsys.err
    assert exc_info.value.code == 1


def test_merge_pr_success(pr_handler, mock_api):
    all_comments = MyFakeResponse(
        200,
        [
            {"body": "/lgtm", "user": {"login": "reviewer1"}},
            {"body": "/lgtm", "user": {"login": "reviewer2"}},
        ],
    )

    all_checks = MyFakeResponse(
        200,
        {
            "check_runs": [
                {
                    "name": "check-1",
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "http://test.url",
                },
            ],
        },
    )

    mock_responses = [
        MyFakeResponse(200, {"permission": "admin"}),
        MyFakeResponse(200, {"head": {"sha": "abc123"}}),
        all_checks,
        MyFakeResponse(200, {}),
        all_comments,
        MyFakeResponse(200, {"permission": "write"}),  # reviewer1
        MyFakeResponse(200, {"permission": "write"}),  # reviewer2
        all_comments,
        MyFakeResponse(200, {"permission": "write"}),  # reviewer1
        MyFakeResponse(200, {"permission": "write"}),  # reviewer2
    ]

    mock_api.get.side_effect = mock_responses

    # Mock successful merge
    mock_api.put.return_value.status_code = 200
    mock_api.post.return_value.status_code = 200

    assert pr_handler.merge_pr() is True

    # Verify merge call
    mock_api.put.assert_called_with(
        "pulls/123/merge",
        {
            "merge_method": "squash",
        },
    )


def test_merge_pr_insufficient_permissions(pr_handler, mock_api):
    # Mock permission check failure
    mock_api.get.return_value.status_code = 200
    mock_api.get.return_value.json.return_value = {"permission": "read"}

    with pytest.raises(SystemExit) as exc_info:
        pr_handler.merge_pr()
    assert exc_info.value.code == 1


def test_merge_pr_failure(pr_handler, mock_api):
    mock_responses = [
        MyFakeResponse(200, {"permission": "peon"}),
    ]
    mock_api.get.side_effect = mock_responses

    # Mock failed merge
    mock_api.put.return_value.status_code = 405
    mock_api.put.return_value.text = "Merge conflict"
    with pytest.raises(SystemExit) as mock_exit:
        assert pr_handler.merge_pr() is False
        assert mock_exit.value.code == 1


def test_post_lgtm_breakdown(pr_handler, mock_api):
    lgtm_users = {"user1": "write", "user2": "read", "user3": "admin"}
    pr_handler._post_lgtm_breakdown(2, lgtm_users)

    # Verify that post_comment was called with the correct breakdown table
    mock_api.post.assert_called()
    call_args = mock_api.post.call_args[0][1]
    assert "| @user1 | `write`" in call_args["body"]
    assert "| @user2 | `read`" in call_args["body"]
    assert "| @user3 | `admin`" in call_args["body"]


def test_check_status(pr_handler, mock_api):
    # Mock successful response with state "open"
    mock_api.get.return_value.status_code = 200
    mock_api.get.return_value.json.return_value = {"state": "open"}
    assert pr_handler.check_status("123", "open") is True
    assert pr_handler.check_status("123", "closed") is False

    # Mock successful response with state "closed"
    mock_api.get.return_value.status_code = 200
    mock_api.get.return_value.json.return_value = {"state": "closed"}
    assert pr_handler.check_status("123", "open") is False
    assert pr_handler.check_status("123", "closed") is True

    # Mock unsuccessful response
    mock_api.get.return_value.status_code = 404
    mock_api.get.return_value.text = "Not Found"
    with pytest.raises(SystemExit) as exc_info:
        pr_handler.check_status("123", "open")
    assert exc_info.value.code == 1


def test_merge_pr_with_custom_method(pr_handler, mock_api):
    all_comments = MyFakeResponse(
        200,
        [
            {"body": "/lgtm", "user": {"login": "reviewer1"}},
            {"body": "/lgtm", "user": {"login": "reviewer2"}},
        ],
    )

    all_checks = MyFakeResponse(
        200,
        {
            "check_runs": [
                {
                    "name": "check-1",
                    "status": "completed",
                    "conclusion": "success",
                    "html_url": "http://test.url",
                },
            ],
        },
    )

    mock_responses = [
        MyFakeResponse(200, {"permission": "admin"}),
        MyFakeResponse(200, {"head": {"sha": "abc123"}}),
        all_checks,
        MyFakeResponse(200, {}),
        all_comments,
        MyFakeResponse(200, {"permission": "write"}),  # reviewer1
        MyFakeResponse(200, {"permission": "write"}),  # reviewer2
        all_comments,
        MyFakeResponse(200, {"permission": "write"}),  # reviewer1
        MyFakeResponse(200, {"permission": "write"}),  # reviewer2
    ]

    mock_api.get.side_effect = mock_responses

    # Mock successful merge
    mock_api.put.return_value.status_code = 200
    mock_api.post.return_value.status_code = 200

    # Test with 'merge' as custom method
    assert pr_handler.merge_pr("merge") is True

    # Verify merge call with custom method
    mock_api.put.assert_called_with(
        "pulls/123/merge",
        {
            "merge_method": "merge",  # Should use the custom method
        },
    )


def test_assign_unassign_pr_author(pr_handler):
    with pytest.raises(SystemExit) as exc_info:
        pr_handler.assign_unassign("assign", ["test_user"])
        assert exc_info == 1


def test_cherry_pick_open_pr(pr_handler, mock_api):
    mock_api.get.return_value = MyFakeResponse(200, {"permission": "admin"})
    mock_api.post.return_value.status_code = 200
    pr_handler.cherry_pick(["release-1.0"])
    mock_api.post.assert_called_with(
        "issues/123/comments",
        {"body": "✅ We will cherry-pick this PR to the branch `release-1.0` upon merge."},
    )


def test_cherry_pick_open_pr_insufficient_permissions(pr_handler, mock_api):
    mock_api.get.return_value = MyFakeResponse(200, {"permission": "read"})
    mock_api.post.return_value = MyFakeResponse(200, {})

    with pytest.raises(SystemExit) as exc_info:
        pr_handler.cherry_pick(["release-1.0"])
    assert exc_info.value.code == 1


def test_cherry_pick_invalid_args(pr_handler):
    with pytest.raises(SystemExit) as exc_info:
        pr_handler.cherry_pick(["branch1", "branch2"])
    assert exc_info.value.code == 1


def test_cherry_pick_immediate_success(pr_handler, mock_api):
    commits = [
        {"sha": "abc123", "commit": {"message": "fix: something"}},
    ]
    mock_responses = [
        MyFakeResponse(200, {"permission": "admin"}),
        MyFakeResponse(200, {"state": "closed", "merged": True, "base": {"ref": "main"}}),
        MyFakeResponse(200, commits),
        MyFakeResponse(200, {"object": {"sha": "target_sha"}}),
    ]
    mock_api.get.side_effect = mock_responses
    mock_api.post.return_value = MyFakeResponse(201, {"sha": "new_sha"})

    pr_handler.cherry_pick(["release-1.0"], immediate=True)

    post_calls = mock_api.post.call_args_list
    assert any(
        "Cherry Pick Successful" in str(call) for call in post_calls
    )


def test_cherry_pick_immediate_closed_not_merged(pr_handler, mock_api):
    mock_responses = [
        MyFakeResponse(200, {"permission": "admin"}),
        MyFakeResponse(200, {"state": "closed", "merged": False}),
    ]
    mock_api.get.side_effect = mock_responses

    with pytest.raises(SystemExit) as exc_info:
        pr_handler.cherry_pick(["release-1.0"], immediate=True)
    assert exc_info.value.code == 1


def test_cherry_pick_immediate_insufficient_permissions(pr_handler, mock_api):
    mock_api.get.return_value = MyFakeResponse(200, {"permission": "read"})
    mock_api.post.return_value = MyFakeResponse(200, {})

    with pytest.raises(SystemExit) as exc_info:
        pr_handler.cherry_pick(["release-1.0"], immediate=True)
    assert exc_info.value.code == 1
