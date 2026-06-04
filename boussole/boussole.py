#!/usr/bin/env python3
# Copyright 2025 Red Hat, Inc.
# Author: Chmouel Boudjnah <chmouel@redhat.com>
#
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "requests",
# ]
# ///
import argparse
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

from .client import GitHubAPI, RequestResponse

from .messages import (  # isort:skip
    APPROVED_TEMPLATE,
    CANNOT_MERGE_OWN_PR,
    CHECKS_NOT_PASSED,
    COMMENTS_FETCH_ERROR,
    HELP_TEXT,
    INSUFFICIENT_PERMISSIONS,
    LGTM_BREAKDOWN_TEMPLATE,
    MERGE_FAILED,
    NOT_ENOUGH_LGTM,
    PERMISSION_CHECK_ERROR,
    PERMISSION_DATA_MISSING,
    SELF_APPROVAL_ERROR,
    SUCCESS_MERGED,
    CHERRY_PICK_ERROR,
    CHERRY_PICK_SUCCESS,
    CHERRY_PICK_CONFLICT,
    REVIEW_REQUESTED,
)


class PRHandler:  # pylint: disable=too-many-instance-attributes
    """
    Handles PR-related operations.
    """

    def __init__(
        self,
        api: GitHubAPI,
        args: argparse.Namespace,
    ):
        self.api = api
        self.pr_num = args.pr_num
        self.pr_sender = args.pr_sender
        self.comment_sender = args.comment_sender
        self.lgtm_threshold = args.lgtm_threshold
        self.lgtm_permissions = args.lgtm_permissions.split(",")
        self.lgtm_review_event = args.lgtm_review_event
        self.merge_method = args.merge_method

        self._pr_status: RequestResponse | None = None

    def check_response(self, resp: RequestResponse) -> bool:
        """
        Checks the response status code and prints an error message if needed.
        """
        if resp.getcode() >= 200 and resp.getcode() < 300:
            return True
        print(
            f"Error while executing the command: status: {resp.getcode()} {resp.read().decode()}",
            file=sys.stderr,
        )
        return False

    def _post_comment(self, message: str) -> RequestResponse:
        """
        Posts a comment to the pull request.
        """
        endpoint = f"issues/{self.pr_num}/comments"
        return self.api.post(endpoint, {"body": message})

    def _fetch_and_validate_lgtm_votes(self) -> Tuple[int, Dict[str, Optional[str]]]:
        """
        Fetches LGTM votes and validates them.

        Returns the number of valid votes and a dictionary of users with their
        permissions.
        """
        reviews_endpoint = f"pulls/{self.pr_num}/reviews"
        reviews_response = self.api.get(reviews_endpoint)
        if reviews_response.status_code != 200:
            error_message = COMMENTS_FETCH_ERROR.format(
                status_code=reviews_response.status_code,
                response_text=reviews_response.text,
                pr_num=self.pr_num,
            )
            print(error_message, file=sys.stderr)
            sys.exit(1)

        lgtm_users: Dict[str, Optional[str]] = {}
        reviews = reviews_response.json()
        for review in reviews:
            if review["state"].lower() == "approved":
                user = review["user"]["login"]
                if user != self.pr_sender:  # Skip self-approvals
                    lgtm_users[user] = None

        endpoint = f"issues/{self.pr_num}/comments"
        response = self.api.get(endpoint)
        if response.status_code != 200:
            error_message = COMMENTS_FETCH_ERROR.format(
                status_code=response.status_code,
                response_text=response.text,
                pr_num=self.pr_num,
            )
            print(error_message, file=sys.stderr)
            sys.exit(1)
        comments = response.json()
        for comment in comments:
            body = comment.get("body", "")
            if re.search(r"^/lgtm\b", body, re.IGNORECASE):
                user = comment["user"]["login"]
                if user == self.pr_sender:
                    msg = SELF_APPROVAL_ERROR.format(
                        user=user, comment_url=comment["html_url"]
                    )
                    self._post_comment(msg)
                    print(msg, file=sys.stderr)
                    sys.exit(1)
                lgtm_users[user] = None

        valid_votes = 0
        for user in lgtm_users:
            permission, is_valid = self._check_membership(user)
            lgtm_users[user] = permission
            if is_valid:
                valid_votes += 1

        return valid_votes, lgtm_users

    def _check_membership(self, user: str) -> Tuple[Optional[str], bool]:
        """
        Checks if a user has the required permissions.
        """
        endpoint = f"collaborators/{user}/permission"
        response = self.api.get(endpoint)
        if response.status_code == 404:  # Handle 404 for missing collaborator
            return None, False
        if response.status_code != 200:
            print(
                PERMISSION_CHECK_ERROR.format(
                    user=user, status_code=response.status_code
                ),
                file=sys.stderr,
            )
            return None, False

        permission = response.json().get("permission")
        if not permission:
            print(
                PERMISSION_DATA_MISSING.format(user=user),
                file=sys.stderr,
            )
            return None, False

        return permission, permission in self.lgtm_permissions

    def _get_pr_commits(self, pr_num: int) -> List[Dict]:
        """
        Fetches all commits from a pull request.
        """
        endpoint = f"pulls/{pr_num}/commits"
        response = self.api.get(endpoint)
        if response.status_code != 200:
            return []
        return response.json()

    def _post_lgtm_breakdown(
        self, valid_votes: int, lgtm_users: Dict[str, Optional[str]]
    ) -> None:
        """
        Posts a detailed breakdown of LGTM votes.
        """
        users_table = ""
        for user, permission in lgtm_users.items():
            is_valid = permission in self.lgtm_permissions
            if "[bot]" in user:
                continue
            valid_mark = "✅" if is_valid else "❌"
            users_table += f"| @{user} | `{permission or 'none'}` | {valid_mark} |\n"

        message = LGTM_BREAKDOWN_TEMPLATE.format(
            valid_votes=valid_votes,
            threshold=self.lgtm_threshold,
            users_table=users_table,
        )
        self._post_comment(message)

    def _get_branch_sha(self, branch: str) -> Optional[str]:
        """
        Gets the SHA of the latest commit on a branch.
        """
        endpoint = f"git/refs/heads/{branch}"
        response = self.api.get(endpoint)
        if response.status_code != 200:
            return None
        return response.json().get("object", {}).get("sha")

    def _create_branch(self, branch_name: str, base_sha: str) -> bool:
        """
        Creates a new branch from the specified SHA.
        """
        endpoint = "git/refs"
        data = {"ref": f"refs/heads/{branch_name}", "sha": base_sha}
        response = self.api.post(endpoint, data)

        return response.status_code == 201

    def _get_pr_status(self, number: int) -> RequestResponse:
        """
        Fetches the status of a pull request.
        """
        if self._pr_status:
            return self._pr_status

        endpoint = f"pulls/{number}"
        self._pr_status = self.api.get(endpoint)
        return self._pr_status

    def _check_runs_status(self) -> Tuple[bool, List[Dict]]:
        """
        Checks if all check runs are successful.

        Returns a tuple of (all_success, failed_checks).
        """
        endpoint = f"commits/{self._get_pr_status(self.pr_num).json()['head']['sha']}/check-runs"
        headers = {"Accept": "application/vnd.github.v3+json"}
        headers.update(self.api.headers)

        response = self.api.get(endpoint)
        if response.status_code != 200:
            return False, []

        check_runs = response.json()["check_runs"]

        failed_checks = [
            {
                "name": check["name"],
                "status": check["status"],
                "conclusion": check["conclusion"],
                "html_url": check["html_url"],
            }
            for check in check_runs
            if check["status"] == "completed"
            and check["conclusion"] not in ["success", "skipped"]
        ]

        pending_checks = [
            {
                "name": check["name"],
                "status": check["status"],
                "html_url": check.get("html_url", ""),
            }
            for check in check_runs
            if check["status"] != "completed"
            and not check["name"].endswith(" / boussole")
        ]

        all_success = not (failed_checks or pending_checks)
        return all_success, failed_checks + pending_checks

    def check_status(self, num: int, status: str) -> bool:
        pr_status = self._get_pr_status(num)
        if pr_status.status_code != 200:
            print(
                f"⚠️ Unable to fetch PR status for PR #{num}: {pr_status.text}",
                file=sys.stderr,
            )
            sys.exit(1)
        return pr_status.json().get("state") == status

    def assign_unassign(self, command: str, users: List[str]) -> RequestResponse:
        """
        Assigns or unassigns users for review with a friendly and informative message.

        Args:
            command (str): Either 'assign' or 'unassign'
            users (List[str]): List of GitHub usernames to assign/unassign

        Returns:
            requests.Response: Response from the GitHub API
        """
        endpoint = f"pulls/{self.pr_num}/requested_reviewers"
        users = [user.lstrip("@") for user in users]
        data = {"reviewers": users}
        method = self.api.post if command == "assign" else self.api.delete
        response = method(endpoint, data)

        for user in users:
            if user == self.pr_sender:
                self._post_comment(
                    message := CANNOT_MERGE_OWN_PR.format(pr_sender=self.pr_sender)
                )
                print(message, file=sys.stderr)
                sys.exit(1)

        if response and response.status_code in [200, 201, 204]:
            if command == "assign":
                # Create a friendly message for assignments
                greeting = "👋 Hello " + ", ".join([f"@{user}" for user in users])
                submitter = self.comment_sender
                message = REVIEW_REQUESTED.format(
                    greeting=greeting, submitter=submitter
                )
            else:
                # Message for unassignment
                message = f"♻️ Removed {', '.join(f'@{user}' for user in users)} from the review list. Thanks for your time!"

            self._post_comment(message)

        return response

    def label(self, labels: List[str]) -> RequestResponse:
        """
        Adds labels to the PR.
        """
        endpoint = f"issues/{self.pr_num}/labels"
        data = {"labels": labels}
        self._post_comment(f"✅ Added labels: <b>{', '.join(labels)}</b>.")
        return self.api.post(endpoint, data)

    def unlabel(self, labels: List[str]) -> RequestResponse:
        """
        Removes labels from the PR.
        """
        for label in labels:
            self.api.delete(f"issues/{self.pr_num}/labels/{label}")
        return self._post_comment(f"✅ Removed labels: <b>{', '.join(labels)}</b>.")

    def cherry_pick(self, values: List[str], immediate: bool = False) -> None:
        """
        Handles cherry-pick command.

        When immediate=False (PR is open): checks permissions, posts an info comment.
        When immediate=True (PR is merged): checks merged state, permissions, then performs cherry-pick.
        """
        if len(values) != 1:
            print(
                f"⚠️ Invalid number of arguments for cherry-pick: {values}",
                file=sys.stderr,
            )
            sys.exit(1)

        target_branch = values[0]

        permission, is_valid = self._check_membership(self.comment_sender)
        if not is_valid:
            msg = INSUFFICIENT_PERMISSIONS.format(
                user=self.comment_sender,
                permission=permission,
                required_permissions=", ".join(self.lgtm_permissions),
            )
            self._post_comment(msg)
            print(msg, file=sys.stderr)
            sys.exit(1)

        if not immediate:
            self._post_comment(
                f"✅ We will cherry-pick this PR to the branch `{target_branch}` upon merge."
            )
            return

        pr_status = self._get_pr_status(self.pr_num).json()
        if not pr_status.get("merged"):
            msg = f"⚠️ PR #{self.pr_num} is closed but not merged. Cannot cherry-pick."
            self._post_comment(msg)
            print(msg, file=sys.stderr)
            sys.exit(1)

        self._perform_cherry_pick(target_branch)

    def rebase(self) -> RequestResponse:
        endpoint = f"pulls/{self.pr_num}/update-branch"
        self._post_comment("✅ Rebased the PR branch on the base branch.")
        return self.api.put(endpoint, {})

    def lgtm(self, send_comment: bool = True) -> int:
        """
        Processes LGTM votes and approves the PR if the threshold is met.

        Includes both comment-based LGTM and direct PR approvals.
        """
        # First check direct PR approvals
        valid_votes, lgtm_users = self._fetch_and_validate_lgtm_votes()
        if valid_votes >= self.lgtm_threshold:
            users_table = ""
            for user, permission in lgtm_users.items():
                is_valid = permission in self.lgtm_permissions
                if "bot" in user:
                    continue
                valid_mark = "✅" if is_valid else "❌"
                users_table += (
                    f"| @{user} | `{permission or 'none'}` | {valid_mark} |\n"
                )
            endpoint = f"pulls/{self.pr_num}/reviews"
            body = APPROVED_TEMPLATE.format(
                pr_sender=self.pr_sender,
                threshold=self.lgtm_threshold,
                valid_votes=valid_votes,
                users_table=users_table,
            )
            data = {"event": self.lgtm_review_event, "body": body}
            print("✅ PR approved with LGTM votes.")
            self.api.post(endpoint, data)
            return valid_votes

        message = NOT_ENOUGH_LGTM.format(
            valid_votes=valid_votes, threshold=self.lgtm_threshold
        )
        print(message)
        if send_comment:
            self._post_lgtm_breakdown(valid_votes, lgtm_users)
        sys.exit(0)

    def merge_pr(self, custom_merge_method: Optional[str] = None) -> bool:
        """
        Merges the PR if it has enough LGTM approvals and all checks are green.

        Args:
            custom_merge_method: If provided, overrides the default merge method.
                                Must be one of: 'merge', 'squash', or 'rebase'.
        """
        # Check if the user has sufficient permissions to merge
        permission, is_valid = self._check_membership(self.comment_sender)
        if not is_valid:
            msg = INSUFFICIENT_PERMISSIONS.format(
                user=self.comment_sender,
                permission=permission,
                required_permissions=", ".join(self.lgtm_permissions),
            )
            self._post_comment(msg)
            print(msg, file=sys.stderr)
            sys.exit(1)

        # Check if all check runs are green
        all_checks_passed, failed_checks = self._check_runs_status()
        if not all_checks_passed:
            status_table = "\n| Check Name | Status |\n|------------|--------|\n"
            for check in failed_checks:
                status = check.get("conclusion", check["status"])
                check_name = check["name"]
                # Add the URL link if available in the check data
                if "html_url" in check:
                    check_name = f"[{check['name']}]({check['html_url']})"
                status_table += f"| {check_name} | `{status}` |\n"

            msg = (
                "⚠️ Cannot merge PR: Some checks are not passing.\n\n"
                f"{status_table}\n\n"
                "Please wait for all checks to pass before merging."
            )
            self._post_comment(CHECKS_NOT_PASSED.format(status_table=status_table))
            print(msg, file=sys.stderr)
            sys.exit(1)

        # Fetch LGTM votes
        valid_votes, lgtm_users = self._fetch_and_validate_lgtm_votes()
        # Handle case where admin/write user can merge directly
        if self.pr_sender != self.comment_sender and permission in [
            "admin",
            "write",
        ]:
            # If threshold is 1, the user with admin/write can merge directly
            # For threshold > 1, count their merge command as a vote if not already counted
            merger_already_voted = self.comment_sender in lgtm_users
            if self.lgtm_threshold == 1 or (
                valid_votes >= self.lgtm_threshold - 1 and not merger_already_voted
            ):
                # Add the merger's vote if not already counted
                if not merger_already_voted:
                    lgtm_users[self.comment_sender] = permission
                    valid_votes += 1
        if valid_votes >= self.lgtm_threshold:
            endpoint = f"pulls/{self.pr_num}/merge"

            # Use custom merge method if provided and valid, otherwise use default
            merge_method = self.merge_method
            if custom_merge_method and custom_merge_method.lower() in [
                "merge",
                "squash",
                "rebase",
            ]:
                merge_method = custom_merge_method.lower()

            data = {
                "merge_method": merge_method,
                # "commit_title": f"Merged PR #{self.pr_num}",
                # "commit_message": f"PR #{self.pr_num} merged by {self.pr_sender} with {valid_votes} LGTM votes.",
            }
            response = self.api.put(endpoint, data)
            if response and response.status_code == 200:
                # Fetch all comments to find cherry-pick commands
                comments_response = self.api.get(f"issues/{self.pr_num}/comments")
                if comments_response.status_code != 200:
                    print(
                        f"⚠️ Unable to fetch comments for PR #{self.pr_num}: {comments_response.text}",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                comments = comments_response.json()
                cherry_pick_branches = set()
                for comment in comments:
                    body = comment.get("body", "")
                    match = re.match(r"^/cherry-pick\s+(\S+)", body, re.IGNORECASE)
                    if match:
                        cherry_pick_branches.add(match.group(1))

                # Perform cherry-picks to the specified branches
                for target_branch in cherry_pick_branches:
                    if not self._perform_cherry_pick(target_branch):
                        return False

                # Create the users table for the success message
                users_table = ""
                for user, permission in lgtm_users.items():
                    is_valid = permission in self.lgtm_permissions
                    if "[bot]" in user:
                        continue
                    valid_mark = "✅" if is_valid else "❌"
                    users_table += (
                        f"| @{user} | `{permission or 'unknown'}` | {valid_mark} |\n"
                    )

                success_message = SUCCESS_MERGED.format(
                    pr_sender=self.pr_sender,
                    merge_method=merge_method,
                    comment_sender=self.comment_sender,
                    valid_votes=valid_votes,
                    lgtm_threshold=self.lgtm_threshold,
                    users_table=users_table,
                )
                self._post_comment(success_message)
                return True

            self._post_comment(
                MERGE_FAILED.format(
                    pr_num=self.pr_num,
                    status_code=response.status_code,
                    error_text=response.text,
                ),
            )
            return False

        self._post_comment(
            NOT_ENOUGH_LGTM.format(
                valid_votes=valid_votes, threshold=self.lgtm_threshold
            ),
        )
        return False

    def _perform_cherry_pick(self, target_branch: str) -> bool:
        """
        Performs cherry-pick operation to the specified branch.
        """
        # Get all PR commits in chronological order
        commits = self._get_pr_commits(self.pr_num)
        if not commits:
            self._post_comment(
                CHERRY_PICK_ERROR.format(
                    source_pr=self.pr_num,
                    target_branch=target_branch,
                    status_code="404",
                    error_text="Could not fetch PR commits",
                )
            )
            return False

        # Check if target branch exists
        current_sha = self._get_branch_sha(target_branch)
        if not current_sha:
            # Handle new branch creation
            pr_info = self._get_pr_status(self.pr_num).json()
            base_branch = pr_info["base"]["ref"]
            base_sha = self._get_branch_sha(base_branch)

            if not base_sha:
                self._post_comment(
                    CHERRY_PICK_ERROR.format(
                        source_pr=self.pr_num,
                        target_branch=target_branch,
                        status_code="404",
                        error_text=f"Could not find base branch: {base_branch}",
                    )
                )
                return False

            if not self._create_branch(target_branch, base_sha):
                self._post_comment(
                    CHERRY_PICK_ERROR.format(
                        source_pr=self.pr_num,
                        target_branch=target_branch,
                        status_code="422",
                        error_text=f"Could not create branch: {target_branch}",
                    )
                )
                return False
            current_sha = base_sha

        # Cherry-pick each commit in sequence
        for i, commit in enumerate(commits, 1):
            endpoint = "merges"
            commit_sha = commit["sha"]
            commit_msg = commit.get("commit", {}).get("message", "")

            data = {
                "base": target_branch,
                "head": commit_sha,
                "commit_message": (
                    f"Cherry-pick: ({i}/{len(commits)}) from PR #{self.pr_num} to {target_branch}\n\n"
                    f"Original commit: {commit_msg}\n"
                    f"Cherry-picked by @{self.comment_sender}"
                ),
            }

            response = self.api.post(endpoint, data)

            if response.status_code == 409:
                # Merge conflict - requires manual intervention
                self._handle_merge_conflict(target_branch, commit_sha, i, len(commits))
                return False  # Indicate cherry-pick was not completed

            if response.status_code != 201:
                self._post_comment(
                    CHERRY_PICK_ERROR.format(
                        source_pr=self.pr_num,
                        target_branch=target_branch,
                        status_code=response.status_code,
                        error_text=response.text,
                    )
                )
                return False  # Indicate cherry-pick was not completed

            # Store new SHA but keep target_branch name unchanged
            current_sha = response.json()["sha"]

        # All commits successfully cherry-picked
        self._post_comment(
            CHERRY_PICK_SUCCESS.format(
                source_pr=self.pr_num,
                target_branch=target_branch,
                user=self.comment_sender,
                commit_sha=current_sha,  # Use final SHA in success message
            )
        )
        return True

    def _handle_merge_conflict(
        self,
        target_branch: str,
        commit_sha: str,
        current_commit: int,
        total_commits: int,
    ) -> None:
        """
        Handles merge conflicts during cherry-pick operation.

        Posts detailed information and instructions for manual resolution.
        """
        conflict_message = CHERRY_PICK_CONFLICT.format(
            pr_num=self.pr_num,
            target_branch=target_branch,
            current_commit=current_commit,
            total_commits=total_commits,
            commit_sha=commit_sha,
        )
        self._post_comment(conflict_message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage prow-like commands on a GitHub PullRequest.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,  # Show default values in help
    )
    # LGTM threshold argument
    parser.add_argument(
        "--lgtm-threshold",
        default=int(os.getenv("PAC_LGTM_THRESHOLD", "1")),  # Default as string
        type=int,
        help="Minimum number of LGTM approvals required to merge a PR. "
        "Can be overridden via the PAC_LGTM_THRESHOLD environment variable.",
    )
    # LGTM permissions argument
    parser.add_argument(
        "--lgtm-permissions",
        default=os.getenv("PAC_LGTM_PERMISSIONS", "admin,write"),
        help="Comma-separated list of GitHub permissions required to give a valid LGTM. "
        "Can be overridden via the PAC_LGTM_PERMISSIONS environment variable.",
    )
    # LGTM review event argument
    parser.add_argument(
        "--lgtm-review-event",
        default=os.getenv("PAC_LGTM_REVIEW_EVENT", "APPROVE"),
        help="The type of review event to trigger when an LGTM is given. "
        "Can be overridden via the PAC_LGTM_REVIEW_EVENT environment variable.",
    )

    # Merge method argument
    parser.add_argument(
        "--merge-method",
        default=os.getenv("GH_MERGE_METHOD", "rebase"),
        help="The method to use when merging the pull request. "
        "Options: 'merge', 'rebase', or 'squash'. "
        "Can be overridden via the GH_MERGE_METHOD environment variable.",
    )
    # GitHub token argument
    parser.add_argument(
        "--github-token",
        default=os.getenv("GITHUB_TOKEN"),
        help="GitHub API token for authentication. "
        "Required if the GITHUB_TOKEN environment variable is not set.",
    )
    # PR number argument
    parser.add_argument(
        "--pr-num",
        default=os.getenv("GH_PR_NUM"),
        help="The number of the pull request to operate on. "
        "Can be overridden via the GH_PR_NUM environment variable.",
    )

    # PR sender argument
    parser.add_argument(
        "--pr-sender",
        default=os.getenv("GH_PR_SENDER"),
        help="The GitHub username of the user who opened the pull request. "
        "Can be overridden via the GH_PR_SENDER environment variable.",
    )

    # Comment sender argument
    parser.add_argument(
        "--comment-sender",
        default=os.getenv("GH_COMMENT_SENDER"),
        help="The GitHub username of the user who triggered the command. "
        "Can be overridden via the GH_COMMENT_SENDER environment variable.",
    )

    # Repository owner argument
    parser.add_argument(
        "--repo-owner",
        default=os.getenv("GH_REPO_OWNER"),
        help="The owner (organization or user) of the GitHub repository. "
        "Can be overridden via the GH_REPO_OWNER environment variable.",
    )

    # Repository name argument
    parser.add_argument(
        "--repo-name",
        default=os.getenv("GH_REPO_NAME"),
        help="The name of the GitHub repository. "
        "Can be overridden via the GH_REPO_NAME environment variable.",
    )

    # Trigger comment argument
    parser.add_argument(
        "--trigger-comment",
        default=os.getenv("PAC_TRIGGER_COMMENT"),
        help="The comment that triggered this command. "
        "Can be overridden via the PAC_TRIGGER_COMMENT environment variable.",
    )

    parsed = parser.parse_args()
    if not parsed.github_token:
        parser.error(
            "GitHub API token is required. Use --github-token or GITHUB_TOKEN env variable."
        )
    if not parsed.pr_num:
        parser.error("PR number is required. Use --pr-num or GH_PR_NUM env variable.")
    if not parsed.pr_sender:
        parser.error(
            "PR sender is required. Use --pr-sender or GH_PR_SENDER env variable."
        )
    if not parsed.comment_sender:
        parser.error(
            "Comment sender is required. Use --comment-sender or GH_COMMENT_SENDER env variable."
        )
    if not parsed.repo_owner:
        parser.error(
            "Repository owner is required. Use --repo-owner or GH_REPO_OWNER env variable."
        )
    if not parsed.repo_name:
        parser.error(
            "Repository name is required. Use --repo-name or GH_REPO_NAME env variable."
        )
    if not parsed.trigger_comment:
        parser.error(
            "Trigger comment is required. Use --trigger-comment or PAC_TRIGGER_COMMENT env variable."
        )
    return parsed


def main():
    args = parse_args()
    # Initialize GitHub API and PR handler
    api_base = f"https://api.github.com/repos/{args.repo_owner}/{args.repo_name}"
    headers = {
        "Authorization": f"Bearer {args.github_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    api = GitHubAPI(api_base, headers)
    pr_handler = PRHandler(api, args)

    trigger_comment = args.trigger_comment.lstrip("\\n")
    match = re.match(
        r"^/(rebase|cherry-pick|merge|assign|unassign|label|unlabel|lgtm|help)(.*)",
        trigger_comment,
    )
    if not match:
        print(
            f"⚠️ No valid command found in comment: {trigger_comment}",
            file=sys.stderr,
        )
        sys.exit(1)

    command, values = match.groups()
    values = values.split()

    pr_is_open = pr_handler.check_status(args.pr_num, "open")

    if not pr_is_open and command != "cherry-pick":
        print(f"⚠️ PR #{args.pr_num} is not open.", file=sys.stderr)
        sys.exit(1)

    response = None
    if command in ("assign", "unassign"):
        response = pr_handler.assign_unassign(command, values)
    elif command == "label":
        response = pr_handler.label(values)
    elif command == "unlabel":
        response = pr_handler.unlabel(values)
    elif command == "rebase":
        response = pr_handler.rebase()
    elif command == "help":
        response = pr_handler._post_comment(HELP_TEXT.strip())
    elif command == "lgtm":
        pr_handler.lgtm()
    elif command == "merge":
        merge_method = (
            values[0]
            if values and values[0].lower() in ["merge", "squash", "rebase"]
            else None
        )
        pr_handler.merge_pr(merge_method)
    elif command == "cherry-pick":
        pr_handler.cherry_pick(values, immediate=not pr_is_open)

    if response:
        if not pr_handler.check_response(response):
            sys.exit(1)


if __name__ == "__main__":
    main()
