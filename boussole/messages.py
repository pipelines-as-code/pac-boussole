import os

LGTM_THRESHOLD = int(os.getenv("PAC_LGTM_THRESHOLD", "1"))

HELP_TEXT = f"""
### 🤖 Available Commands
| Command                     | Description                                                                     |
| --------------------------- | ------------------------------------------------------------------------------- |
| `/assign user1 user2`       | Assigns users for review to the PR                                              |
| `/unassign user1 user2`     | Removes assigned users                                                          |
| `/label bug feature`        | Adds labels to the PR                                                           |
| `/unlabel bug feature`      | Removes labels from the PR                                                      |
| `/lgtm`                     | Approves the PR if at least {LGTM_THRESHOLD} org members have commented `/lgtm` |
| `/merge [method]`           | Merges the PR if approvals are sufficient. Admin/write users can merge directly with threshold=1 |
| `/cherry-pick target-branch`| Cherry-picks the PR changes to the target branch                                |
| `/rebase`                   | Rebases the PR branch on the base branch                                        |
| `/help`                     | Shows this help message                                                         |


*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""

HELP_TOPIC_TEMPLATES = {
    "assign": """
### `/assign` Help

**Syntax:** `/assign user1 [user2 ...]`

**Example:** `/assign octocat monalisa`

**Permissions:** The configured GitHub token must be allowed to request reviewers.

**Side effects:** Requests the listed users as reviewers and posts a review-request comment. The PR author cannot be assigned.
""",
    "unassign": """
### `/unassign` Help

**Syntax:** `/unassign user1 [user2 ...]`

**Example:** `/unassign octocat monalisa`

**Permissions:** The configured GitHub token must be allowed to manage requested reviewers.

**Side effects:** Removes the listed users from the PR's requested reviewers and posts a confirmation comment.
""",
    "label": """
### `/label` Help

**Syntax:** `/label label1 [label2 ...]`

**Example:** `/label bug needs-review`

**Permissions:** The configured GitHub token must be allowed to manage issue and PR labels.

**Side effects:** Adds the listed labels to the PR and posts a confirmation comment.
""",
    "unlabel": """
### `/unlabel` Help

**Syntax:** `/unlabel label1 [label2 ...]`

**Example:** `/unlabel needs-review`

**Permissions:** The configured GitHub token must be allowed to manage issue and PR labels.

**Side effects:** Removes the listed labels from the PR and posts a confirmation comment.
""",
    "lgtm": """
### `/lgtm` Help

**Syntax:** `/lgtm`

**Example:** `/lgtm`

**Permissions:** A vote counts only when the reviewer has one of these repository permissions: `{permissions}`. Self-approval is rejected. The configured threshold is **{threshold}**.

**Side effects:** Records the comment as an approval signal, submits a `{review_event}` review when configured, and posts the current vote breakdown.
""",
    "merge": """
### `/merge` Help

**Syntax:** `/merge [merge|squash|rebase]`

**Examples:** `/merge` or `/merge squash`

**Permissions:** The caller must have one of these repository permissions: `{permissions}`. The PR needs **{threshold}** valid approval(s), unless the configured direct-merge rules apply.

**Side effects:** Verifies required checks and approvals, then merges with the requested method or the configured `{merge_method}` default. Any queued `/cherry-pick` requests are processed after the merge.
""",
    "cherry-pick": """
### `/cherry-pick` Help

**Syntax:** `/cherry-pick target-branch`

**Example:** `/cherry-pick release-v1.2`

**Permissions:** The configured GitHub token must be allowed to read commits and update the target branch.

**Side effects:** Queues the PR commits to be cherry-picked to the target branch after the PR is merged. Conflicts require manual resolution.
""",
    "rebase": """
### `/rebase` Help

**Syntax:** `/rebase`

**Example:** `/rebase`

**Permissions:** The configured GitHub token and repository settings must allow the PR branch to be updated.

**Side effects:** Requests GitHub to update the PR branch from its base branch and posts a confirmation comment.
""",
    "help": """
### `/help` Help

**Syntax:** `/help [command]`

**Examples:** `/help` or `/help merge`

**Permissions:** Any user who can trigger the Boussole pipeline may request help.

**Side effects:** Posts either the general command table or detailed help for one command. It does not modify the PR.
""",
}

UNKNOWN_HELP_TOPIC = """
### Unknown Help Topic

No detailed help is available for `{topic}`.

{general_help}
"""

APPROVED_TEMPLATE = """
Congrats @{pr_sender} your PR Has been approved 🎉

### ✅ Pull Request Approved

*Approval Status:* 
* Required Approvals: {threshold}
* Current Approvals: {valid_votes}

### 👥 Reviewers Who Approved:
| Reviewer | Permission Level | Approval Status |
|----------|------------------|----------------|
{users_table}

### 📝 Next Steps
* Ensure all required checks pass
* Comply with branch protection rules
* Request a maintainer to merge using the `/merge` command (or merge it
directly if you have repository permission).


*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""

LGTM_BREAKDOWN_TEMPLATE = """
### LGTM Vote Breakdown

* **Current valid votes:** {valid_votes}/{threshold}
* **Voting required for approval:** {threshold}

*Votes Summary:* 
| Reviewer | Permission | Valid Vote |
|----------|------------|------------|
{users_table}


*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""

SUCCESS_MERGED = """
### ✅ PR Successfully Merged

* Merge method: `{merge_method}`
* Merged by: **@{comment_sender}**
* Total approvals: **{valid_votes}/{lgtm_threshold}**

**Approvals Summary:**
| Reviewer | Permission | Status |
|----------|------------|--------|
{users_table}


Thank you @{pr_sender} for your valuable contribution! 🎉

*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""

# Error and status message templates
PERMISSION_CHECK_ERROR = """
### ⚠️ Permission Check Failed

Unable to verify permissions for user **@{user}**
* API Response Status: `{status_code}`
* This might be due to:
  * User not being a repository collaborator
  * Invalid authentication
  * Rate limiting

Please check user permissions and try again.


*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""

PERMISSION_DATA_MISSING = """
### ❌ Permission Data Missing

Failed to retrieve permission level for user **@{user}**
* Received empty permission data from GitHub API
* This might indicate an API response format change
* Please contact repository administrators for assistance


*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""

COMMENTS_FETCH_ERROR = """
### 🚫 Failed to Retrieve PR Comments

Unable to process LGTM votes due to API error:
* Status Code: `{status_code}`
* Response: `{response_text}`

*Troubleshooting Steps:* 
1. Check your authentication token
2. Verify PR number: `{pr_num}`
3. Ensure the PR hasn't been closed or deleted


*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""

SELF_APPROVAL_ERROR = """
### ⚠️ Invalid LGTM Vote

* User **@{user}** attempted to approve their own PR
* Self-approval is not permitted for security reasons
* Please [delete the comment]({comment_url}) before continuing.

Please wait for reviews from other team members.


*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""

CANNOT_MERGE_OWN_PR = """
### 🤦‍♂️ You can't assign the PR to @{pr_sender}

The user @{pr_sender} is the author of this Pull Request.

Nice try though! Authors reviewing their own code is like grading your own exam
- tempting but defeats the purpose! 😉

*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 
"""

INSUFFICIENT_PERMISSIONS = """
### 🔒 Insufficient Permissions

* User **@{user}** does not have permission to merge
* Current permission level: `{permission}`
* Required permissions: `{required_permissions}`

Please request assistance from a repository maintainer.

*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 
"""

NOT_ENOUGH_LGTM = """
### ❌ Insufficient Approvals

* Current valid LGTM votes: **{valid_votes}** 
* Required votes: **{threshold}**

Please obtain additional approvals before merging.


*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""

MERGE_FAILED = """
### ❌ Merge Failed

Unable to merge PR #{pr_num}:
* Status Code: `{status_code}`
* Error: `{error_text}`

*Possible causes:* 
* Branch protection rules not satisfied
* Merge conflicts present
* Required checks failing

Please resolve any issues and try again.

*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 
"""

# Add new error message template for cherry-pick
CHERRY_PICK_ERROR = """
### ❌ Cherry Pick Failed

Failed to cherry-pick changes from PR #{source_pr} to branch `{target_branch}`:
* Status Code: `{status_code}`
* Error: `{error_text}`

*Possible causes:* 
* Merge conflicts
* Branch protection rules
* Invalid branch name
* Missing permissions

Please resolve any issues and try again.

*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""

CHERRY_PICK_SUCCESS = """
### ✅ Cherry Pick Successful

Successfully cherry-picked changes from PR #{source_pr} to branch `{target_branch}`.

*Details:* 
* Source PR: #{source_pr}
* Target Branch: `{target_branch}`
* Cherry-picked by: @{user}
* New commit SHA: `{commit_sha}`


*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""

CHERRY_PICK_CONFLICT = """
🚨 Merge conflict detected while cherry-picking PR #{self.pr_num} to {target_branch}
• Progress: {current_commit}/{total_commits} commits
• Conflicting commit: {commit_sha}

To resolve this conflict:
1. Create a new branch from {target_branch}

```shell
git checkout -b resolve-cherry-pick-{self.pr_num} origin/{target_branch}
```

2. Cherry-pick the commits manually using:

```shell
git cherry-pick {commit_sha}
```

3. Resolve the conflicts with your favorite editor
4. Create a new PR with your changes

```shell
git push YOURFORKREMOTE resolve-cherry-pick-{self.pr_num} --force-with-lease
gh pr create --base {target_branch} --head YOURFORK:resolve-cherry-pick-{self.pr_num}

```

Need assistance? Please contact the repository maintainers.


*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""

REVIEW_REQUESTED = """{greeting}

🔍 @{submitter} has kindly requested your review on this PR. 

• Please review the changes and provide your feedback
• Look for code quality, potential bugs, and overall design
• Feel free to suggest improvements or alternatives
• Consider testing the changes if possible

⏰ Take your time - there's no immediate rush, but a timely review would be
appreciated.

Thank you for your help! 🙌


*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 

"""


CHECKS_NOT_PASSED = """⚠️ Cannot merge PR: Some required checks haven't completed successfully.

{status_table}

🔍 Please ensure all checks pass before merging.
💡 Tip: Review the failing checks above and address any issues.

*Automated by the [PAC Boussole](https://github.com/openshift-pipelines/pac-boussole) 🧭* 
"""
