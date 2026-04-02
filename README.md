# PAC Boussole - A GitOps Command Tool for GitHub PRs

<p align="center">
  <img alt="Boussole logo" src="https://github.com/user-attachments/assets/1fef492b-3b40-4ef8-a934-b9a76517973e" width="25%" height="25%">
</p>

> [!CAUTION]
> This product is not actively maintained by its creator and is provided on an "as-is" basis, without any official support or guarantees.

## Overview

**PAC Boussole** extends GitHub Pull Requests with command-based automation
powered by [Tekton Pipelines](https://tekton.dev/). Inspired by
[Prow](https://github.com/kubernetes/test-infra/tree/master/prow), Boussole
lets you interact with PRs using predefined GitHub comments to trigger
automated actions.

### Key Features

- Automate PR actions such as merging, assigning reviewers, labeling, and more.
- Works seamlessly with Pipelines-as-Code and Tekton.
- Uses GitHub comments to trigger actions, reducing manual intervention.
- Designed for teams leveraging GitOps workflows.

## Supported Commands

| Command                      | Description                                                      |
|------------------------------|------------------------------------------------------------------|
| `/assign user1 user2`        | Assigns users for review to the PR                              |
| `/unassign user1 user2`      | Removes assigned users                                          |
| `/label bug feature`         | Adds labels to the PR                                           |
| `/unlabel bug feature`       | Removes labels from the PR                                      |
| `/cherry-pick target-branch` | Cherry-picks the PR changes to the target branch on merge      |
| `/lgtm`                      | Approves the PR if at least one org member has commented `/lgtm` |
| `/merge [method]`            | Merges the PR if it has enough `/lgtm` approvals. Optional method: `merge`, `squash`, or `rebase` |
| `/rebase`                    | Rebases the PR branch on the base branch                        |
| `/help`                      | Displays available commands                                     |

> **Note:**
>
> - Each command must be issued as a separate comment (no multiple commands per
>   comment yet).
> - The command must be at the start of the comment; any preceding text will be
>   ignored.

## Usage

To enable Boussole, add the following `PipelineRun` configuration to your `.tekton` directory:

```yaml
apiVersion: tekton.dev/v1
kind: PipelineRun
metadata:
  name: boussole
  annotations:
    pipelinesascode.tekton.dev/pipeline: "https://raw.githubusercontent.com/openshift-pipelines/pac-boussole/main/pipeline-boussole.yaml"
    pipelinesascode.tekton.dev/on-comment: "^/(help|rebase|lgtm|cherry-pick|assign|merge|unassign|label|unlabel)"
    pipelinesascode.tekton.dev/max-keep-runs: "2"
spec:
  params:
    - name: trigger_comment
      value: |
        {{ trigger_comment }}
    - name: repo_owner
      value: "{{ repo_owner }}"
    - name: repo_name
      value: "{{ repo_name }}"
    - name: pull_request_number
      value: "{{ pull_request_number }}"
    - name: pull_request_sender
      value: "{{ body.issue.user.login }}"
    - name: git_auth_secret
      value: "{{ git_auth_secret }}"
    - name: comment_sender
      value: "{{ sender }}"
    #
    # Optional parameters (value is the default):
    #
    # The key in git_auth_secret that contains the token (default: git-provider-token)
    # - name: git_auth_secret_key
    #   value: git-provider-token
    #
    # The /lgtm threshold needed of approvers for a PR to be approved (default: 1)
    # - name: lgtm_threshold
    #   value: "1"
    #
    # The permissionms the user need to trigger a lgtm
    # - name: lgtm_permissions
    #   value: "admin,write"
    #
    # The review event  when lgtm is triggered, can be APPROVE,
    # REQUEST_CHANGES, or COMMENT if setting to empty string it will be set as
    # PENDING
    # - name: lgtm_review_event
    #   value: "APPROVE"
    #
    # The merge method to use. Can be one of: merge, squash, rebase
    # - name: merge_method
    #   value: "rebase"
  pipelineRef:
    name: boussole
```

### Without Pipelines-as-Code

You can also use this pipeline independently via Tekton Triggers. Simply
configure a `TriggerTemplate` with the required parameters.

(Contributions welcome! Feel free to add examples for alternative usage.)

## Contributing

We welcome contributions! Feel free to open issues or submit pull requests.

### Development Setup

1. Install [uv](https://github.com/astral-sh/uv).
2. Use the provided Makefile targets for common tasks.
3. Set up pre-commit hooks:

   ```sh
   pre-commit install
   ```

   This ensures your commits adhere to project guidelines.

## FAQ

### Why the name "Boussole"?

**Boussole** is French for *"compass,"* reflecting its role in guiding PR workflows. The name also pays homage to [La
Boussole](<https://en.wikipedia.org/wiki/French_ship_Boussole_(1782)>, a ship from the ill-fated La Pérouse expedition that disappeared
in the Pacific—an analogy that may feel more or less fitting, depending on your experience with this project. 😉  

**Pronunciation:** *Boussole* is pronounced **"boo-SOHL"** (/buˈsɔl/).  

- Sounds like **"boo-soul"** in English.  
- The **"bou"** rhymes with *boo* (as in *boost* or *book*).  
- The **"ssole"** sounds like *soul*, but with a softer "L" at the end.

<p align="center">
  <img alt="Boussole logo" src="https://github.com/user-attachments/assets/2224611a-6bb9-4c5c-9426-77efc996b6ca" width="25%" height="25%">
</p>

## License

PAC Boussole is licensed under [Apache-2.0](./LICENSE).
