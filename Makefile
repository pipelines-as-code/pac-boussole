# Variables for testing
CMD =
ARGS=
UVCMD = uv run
PIPELINE_PROW = pipeline-boussole.yaml
GH_REPO_OWNER = pipelines-as-code
GH_REPO_NAME = pac-boussole
GH_PR_NUM = 44
GH_PR_SENDER = anotheruser
GH_COMMENT_SENDER = chmouel
PASS_TOKEN = github/chmouel-token
PRURL = https://github.com/$(GH_REPO_OWNER)/$(GH_REPO_NAME)/pull/$(GH_PR_NUM)
CONTAINER_IMAGE = ghcr.io/pipelines-as-code/pac-boussole:nightly
PYTEST = pytest
PYLINT = pylint
PYTEST_ARGS = --cov=boussole --cov-report=term

# Phony targets
.PHONY: test directtest open_pr help

test: ## Run tests with pytest
	@$(PYTEST) -v boussole $(PYTEST_ARGS) $(ARGS)

lint:
	@$(PYLINT) boussole

directtest: ## Run a specific command directly (e.g., make directtest CMD=/lgtm)
	@[[ -n "$(CMD)" ]] || (echo "Please specify a command to run as argument: like 'make directtest CMD=/lgtm'" && exit 1)
	@env GH_PR_NUM=$(GH_PR_NUM) GH_REPO_NAME=$(GH_REPO_NAME) GH_REPO_OWNER=$(GH_REPO_OWNER) \
		GH_PR_SENDER=$(GH_PR_SENDER) GH_COMMENT_SENDER=$(GH_COMMENT_SENDER) \
		PAC_TRIGGER_COMMENT="$(CMD)" GITHUB_TOKEN=`pass show $(PASS_TOKEN)` \
		./pac-boussole

open_pr: ## Open the PR in the browser
	@if type -p xdg-open > /dev/null; then xdg-open $(PRURL); \
	elif type -p open > /dev/null; then open $(PRURL); \
	else echo "No supported browser opener found (xdg-open or open)"; fi

help: ## Display this help message
	@python3 -c "import re, sys; \
	targets = [m.groups() for m in re.finditer(r'^([a-zA-Z0-9_-]+):.*?## (.*)$$', sys.stdin.read(), re.MULTILINE)]; \
	print('\n'.join(sorted([f'\033[36m{target:<17}\033[0m {desc}' for target, desc in targets])))" < $(MAKEFILE_LIST)
