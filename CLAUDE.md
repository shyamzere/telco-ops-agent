# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Learning project: a Strands agent queries **fake** telco data in Snowflake through a custom MCP server. It runs locally, in AWS Lambda (Terraform in `infra/`), and behind a Streamlit demo UI (`app.py`). It is a work in progress, developed day by day. There are no tests or linter yet. CI exists (see below) but only checks formatting, validity and that Python compiles.

## Rules

- Fake data only. Never add real data.
- The agent's Snowflake role (`AGENT_READONLY`) must stay read-only (see guardrails below).
- Never read or print anything in `~/.telco-keys` (on Windows: `C:\Users\shyam\.telco-keys`) or `~/.aws`. `.claude/settings.json` also denies these reads.
- Never commit secrets, keys, `.env` files, `terraform.tfvars` or Terraform state.
- Run Python with `uv run`. The AWS region is `ap-southeast-2`.
- `git push` needs the user's approval (`ask` rule in `.claude/settings.json`); `terraform apply`/`destroy` are denied.
- The user is learning: explain what you change and why.

## Commands

Python 3.13, managed with `uv` (not pip).

```sh
uv sync                                                    # install deps (removes the ui group)
uv sync --group ui                                         # install deps plus Streamlit
uv run python -m telco_ops_agent.agent "<question>"        # single analyst agent
uv run python -m telco_ops_agent.multi "<question>"        # orchestrator (analyst + writer)
uv run --group ui streamlit run app.py                     # demo UI (also VS Code Ctrl+Shift+B, see .vscode/tasks.json)
uv run mcp dev src/telco_ops_agent/server.py               # inspect MCP tools on their own
uv run scripts/test_snowflake.py                           # Snowflake connection smoke test
uv run hello.py                                            # Bedrock access check, no tools
uv run python scripts/build_lambda.py                      # build build/lambda/lambda.zip
uv run python -m compileall -q src scripts app.py hello.py # what CI runs for Python
terraform -chdir=infra fmt -check -recursive               # what CI runs for Terraform (plus validate)
```

Running the agents needs live AWS Bedrock credentials (`ap-southeast-2`) and the Snowflake private key at `~/.telco-keys/agent_key.p8`. `server.py` honours `SNOWFLAKE_KEY_PATH` to override that path, and `agent.py` forwards that variable to the MCP subprocess explicitly (the stdio client does not pass the parent environment). `scripts/test_snowflake.py` does **not** honour it (it always uses the default path).

## Architecture

Snowflake setup SQL lives in `sql/setup.sql`, and helper scripts in `scripts/`. The Python package is under `src/telco_ops_agent/`:

1. **`server.py`**: a FastMCP stdio server exposing `list_tables`, `describe_table` and `run_query` over Snowflake `TELCO_DB.OPS`. It opens a new connection per call, using key-pair auth as `AGENT_SVC` with the `AGENT_READONLY` role. Session parameters set a 30 s statement timeout and `TIMEZONE = Pacific/Auckland`.
2. **`agent.py`**: defines the shared `model` (Strands `BedrockModel`, Claude Haiku 4.5 via the `au.` inference profile), the analyst `SYSTEM_PROMPT`, `make_client()` and `ask()`. `make_client()` launches `server.py` as a subprocess using `sys.executable`, so the agent never connects to Snowflake directly.
3. **`multi.py`**: imports `model`, `SYSTEM_PROMPT` and `make_client` from `agent.py`. It wraps an analyst agent (with MCP tools) and a writer agent (no tools) as `@tool` functions, and passes both to an orchestrator agent. Sub-agents use `callback_handler=None`. `multi.ask()` runs one question end to end and is used by both `__main__` and `app.py`.
4. **`lambda_handler.py`**: Lambda entry point. Runs `agent.ask()` (single agent only). On cold start it reads the Snowflake key from the SSM SecureString `/telco-ops/snowflake-private-key`, writes it to `/tmp` with `0600`, and sets `SNOWFLAKE_KEY_PATH`. It sets `HOME=/tmp` before imports.

Changing the model or the analyst prompt in `agent.py` therefore affects every entry point. If you change the model, also change `model_id` in `infra/variables.tf` (IAM is scoped to it).

**`app.py`** (repo root) is a Streamlit demo UI with three modes: `agent.ask()` locally, `multi.ask()` locally, or a boto3 invoke of the `telco-ops-agent` Lambda (150 s read timeout, no retries). Streamlit is in the `ui` dependency group, so `uv export --no-dev` in `scripts/build_lambda.py` leaves it out of the Lambda zip. Keep it that way. The UI shows friendly error messages only, never stack traces, env vars or secrets.

The same MCP server is also registered for Claude Code in `.mcp.json` (as `telco-ops`), so Claude Code can query the fake data directly with the same read-only tools.

## Infrastructure and CI

- `infra/` (Terraform, local state, gitignored): private S3 bucket for the zip, the Lambda function (Python 3.13, x86_64, 1024 MB, 120 s), its log group (7 day retention), an IAM role with one least-privilege inline policy, and a 5 USD monthly budget. `budget_email` comes from the gitignored `terraform.tfvars`.
- The SSM key parameter is created with the AWS CLI, **not** Terraform, so the key never enters state. Do not add an `aws_ssm_parameter` resource or data source for it.
- Bedrock IAM allows the inference profile plus the foundation model in each region in `bedrock_destination_regions`. Keep that list matching the profile's real destination regions.
- `.github/workflows/ci.yml` runs on push and PR with `contents: read` and no AWS credentials. Terraform job: `fmt -check`, `init -backend=false`, a placeholder `lambda.zip`, `validate`. Python job: `uv sync`, then `compileall` on `src`, `scripts`, `app.py`, `hello.py`.

## Read-only guardrails (keep these intact)

The agent must never be able to modify data. Safety is layered, and changes should not weaken any layer:

- The analyst and orchestrator prompts tell the agent to politely refuse any request to change data, without calling a tool.
- `run_query` checks every query: it allows a single statement only, which must start with `SELECT`/`WITH`, and rejects any query containing a keyword from the `BLOCKED` regex.
- The Snowflake role `AGENT_READONLY` has only `USAGE`/`SELECT` grants (see `sql/setup.sql`).
- Results are capped at `MAX_ROWS` (100) with a `truncated` flag, and there's a 30 s statement timeout.
- Prompts require every number to come from query results.

## Snowflake specifics

- The account ID `XAFPDTM-VV71865` is hardcoded in both `server.py` and `scripts/test_snowflake.py`. Keep them in sync.
- `sql/setup.sql` creates the warehouse (XSMALL, 5-credit monthly resource monitor), random sample data (SITES 60, INCIDENTS 3000, TICKETS 5000) and the read-only role. It does **not** create the `AGENT_SVC` user; that step is documented in the README.
- `sql/setup.sql` grants `AGENT_READONLY` to the user `"shyamzere"` so the role can be tested from a worksheet. Anyone else running it must change that name. Test with `USE SECONDARY ROLES NONE`, or secondary roles hide missing grants.
- `TICKETS` has no priority or status column, and `INCIDENTS` has no status column.
- `BLOCKED` is a whole-word, case-insensitive match, so it also rejects harmless queries that use those words as identifiers or inside string literals (e.g. `WHERE CAUSE = 'Power reset'` is fine, but `'set'` or a column named `UPDATE` is not). That is an accepted trade-off: prefer false rejections over loosening the check.
- The sample data is regenerated randomly, so exact counts and values differ between setups.
