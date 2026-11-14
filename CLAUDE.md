# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

Learning project: a Strands agent queries **fake** telco data in Snowflake through a custom MCP server. It is a work in progress, developed day by day. Expect incomplete pieces: e.g. the `telco-ops-agent` console script in `pyproject.toml` is still a placeholder, and there are no tests or linter configured yet.

## Rules

- Fake data only. Never add real data.
- The agent's Snowflake role (`AGENT_READONLY`) must stay read-only (see guardrails below).
- Never read or print anything in `C:\Users\shyam\.telco-keys` or `~/.aws`.
- Never commit secrets, keys or `.env` files.
- Run Python with `uv run`. The AWS region is `ap-southeast-2`.
- The user is learning: explain what you change and why.

## Commands

Python 3.13, managed with `uv` (not pip).

```sh
uv sync                                                    # install deps
uv run python -m telco_ops_agent.agent "<question>"        # single analyst agent
uv run python -m telco_ops_agent.multi "<question>"        # orchestrator (analyst + writer)
uv run mcp dev src/telco_ops_agent/server.py               # inspect MCP tools on their own
uv run scripts/test_snowflake.py                           # Snowflake connection smoke test
uv run hello.py                                            # Bedrock access check, no tools
```

Running the agents needs live AWS Bedrock credentials (`ap-southeast-2`) and the Snowflake private key at `~/.telco-keys/agent_key.p8` (override with `SNOWFLAKE_KEY_PATH`).

## Architecture

Snowflake setup and check SQL lives in `sql/`, and helper scripts in `scripts/`. The code is three layers, each in one file under `src/telco_ops_agent/`:

1. **`server.py`**: a FastMCP stdio server exposing `list_tables`, `describe_table` and `run_query` over Snowflake `TELCO_DB.OPS`. It opens a new connection per call, using key-pair auth as `AGENT_SVC` with the `AGENT_READONLY` role.
2. **`agent.py`**: defines the shared `model` (Strands `BedrockModel`, Claude Haiku 4.5 via the `au.` inference profile), the analyst `SYSTEM_PROMPT`, and `make_client()`. `make_client()` launches `server.py` as a subprocess using `sys.executable`, so the agent never connects to Snowflake directly.
3. **`multi.py`**: imports `model`, `SYSTEM_PROMPT` and `make_client` from `agent.py`. It wraps an analyst agent (with MCP tools) and a writer agent (no tools) as `@tool` functions, and passes both to an orchestrator agent. Sub-agents use `callback_handler=None`, so only the orchestrator streams output.

Changing the model or the analyst prompt in `agent.py` therefore affects both entry points.

The same MCP server is also registered for Claude Code in `.mcp.json` (as `telco-ops`), so Claude Code can query the fake data directly with the same read-only tools.

## Read-only guardrails (keep these intact)

The agent must never be able to modify data. Safety is layered, and changes should not weaken any layer:
- The Snowflake role `AGENT_READONLY` has only `USAGE`/`SELECT` grants (see `sql/setup.sql`).
- `run_query` checks every query: it allows a single statement only, which must start with `SELECT`/`WITH`, and rejects any query containing a keyword from the `BLOCKED` regex.
- Results are capped at `MAX_ROWS` (100) with a `truncated` flag, and there's a 30 s statement timeout.
- Prompts require every number to come from query results.

## Snowflake specifics

- The account ID `XAFPDTM-VV71865` is hardcoded in both `server.py` and `scripts/test_snowflake.py`. Keep them in sync.
- `sql/setup.sql` creates the warehouse (XSMALL, 5-credit monthly resource monitor), random sample data (SITES 60, INCIDENTS 3000, TICKETS 5000) and the read-only role. It does **not** create the `AGENT_SVC` user; that step is documented in the README.
- The sample data is regenerated randomly, so exact counts and values differ between setups.
