# telco-ops-agent

An AI analyst for a telco network operations team. Ask a question in plain English ("Which region has the most critical incidents?") and an agent queries a Snowflake database of sites, incidents and support tickets, then answers with the SQL it ran.

Built with [Strands Agents](https://strandsagents.com/), Claude Haiku 4.5 on Amazon Bedrock, and a small [MCP](https://modelcontextprotocol.io/) server that gives the agent **read-only** access to Snowflake.

## How it works

```
                 ┌──────────────── multi.py ────────────────┐
question ──────► │ Orchestrator                             │
                 │   ├─► analyst_agent ──► MCP tools ───────┼──► Snowflake (TELCO_DB.OPS)
                 │   └─► writer_agent (manager summary)     │       read-only role
                 └──────────────────────────────────────────┘
```

| File | Purpose |
| --- | --- |
| [src/telco_ops_agent/server.py](src/telco_ops_agent/server.py) | MCP server (stdio) with three tools: `list_tables`, `describe_table`, `run_query` |
| [src/telco_ops_agent/agent.py](src/telco_ops_agent/agent.py) | Single analyst agent. Explores the schema, writes SQL and answers with numbers taken from the query results |
| [src/telco_ops_agent/multi.py](src/telco_ops_agent/multi.py) | Multi-agent orchestrator. Sends the question to the analyst, then to a writer that produces a summary of at most 3 sentences for a manager |
| [sql/setup.sql](sql/setup.sql) | Snowflake setup: warehouse, spending cap, sample data, read-only role |
| [scripts/gen_keys.py](scripts/gen_keys.py) | Generates the RSA key pair used for Snowflake key-pair auth |
| [scripts/test_snowflake.py](scripts/test_snowflake.py) | Connection smoke test |
| [hello.py](hello.py) | Minimal Strands + Bedrock check, no tools |

### Data model

Sample data generated randomly in `TELCO_DB.OPS`:

- **SITES** (60 rows): `SITE_ID`, `SITE_NAME`, `REGION` (Auckland, Waikato, Wellington, Canterbury, Otago), `TECHNOLOGY` (4G/5G)
- **INCIDENTS** (3,000 rows): `INCIDENT_ID`, `SITE_ID`, `SEVERITY` (Low to Critical), `CAUSE`, `START_TIME`, `DURATION_MINUTES`
- **TICKETS** (5,000 rows): `TICKET_ID`, `SITE_ID`, `CATEGORY`, `CREATED_AT`, `RESOLUTION_MINUTES`

All timestamps fall within the last 90 days.

## Safety guardrails

The agent can only read data. This is enforced in layers:

1. **Snowflake role**: the agent connects as `AGENT_SVC` with the `AGENT_READONLY` role, which has only `USAGE` and `SELECT` grants.
2. **Query validation** in `run_query`: one statement only, must start with `SELECT` or `WITH`, and is rejected if it contains write or DDL keywords (`insert`, `drop`, `grant`, ...).
3. **Limits**: at most 100 rows are returned (with a `truncated` flag), and statements time out after 30 seconds.
4. **Cost cap**: the `TELCO_RM` resource monitor allows 5 credits/month and suspends the XSMALL warehouse at 100%. The warehouse auto-suspends after 60 s idle.
5. **Prompting**: the agents are told to base every number on query results and never guess.

## Setup

### Prerequisites

- Python 3.13 and [uv](https://docs.astral.sh/uv/)
- A Snowflake account with `ACCOUNTADMIN`
- AWS credentials with Bedrock access to Claude Haiku 4.5 in `ap-southeast-2` (the `au.` cross-region inference profile)

### 1. Install

```sh
uv sync
```

### 2. Create the Snowflake objects

Run [sql/setup.sql](sql/setup.sql) in a Snowflake worksheet as `ACCOUNTADMIN`. It ends by checking that the read-only role **cannot** delete; that final `DELETE` is expected to fail.

### 3. Create the service user and key

Generate a key pair. The private key is written to `~/.telco-keys/agent_key.p8` and the public key is printed:

```sh
uv run scripts/gen_keys.py
```

Create the service user in Snowflake. `setup.sql` doesn't do this step:

```sql
USE ROLE ACCOUNTADMIN;
CREATE USER IF NOT EXISTS AGENT_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = AGENT_READONLY
  RSA_PUBLIC_KEY = '<paste the printed public key>';
GRANT ROLE AGENT_READONLY TO USER AGENT_SVC;
```

### 4. Configure

- The Snowflake account identifier is hardcoded as `ACCOUNT` in [server.py](src/telco_ops_agent/server.py) and in [test_snowflake.py](scripts/test_snowflake.py). Change it to your own account.
- To keep the private key elsewhere, set `SNOWFLAKE_KEY_PATH`. The default is `~/.telco-keys/agent_key.p8`.
- AWS credentials are taken from the standard boto3 chain (`aws login`, `AWS_PROFILE`, env vars, ...).

### 5. Verify

```sh
uv run scripts/test_snowflake.py   # prints ('AGENT_SVC', 'AGENT_READONLY', 3000)
uv run hello.py                    # checks Bedrock access
```

## Usage

Single analyst agent:

```sh
uv run python -m telco_ops_agent.agent "Which cause leads to the longest critical incidents?"
```

Orchestrator with the manager-friendly summary:

```sh
uv run python -m telco_ops_agent.multi "How many 5G sites in Auckland had a fibre cut in the last 30 days?"
```

With no question, both default to *"Which region has the most critical incidents?"*.

The agent starts the MCP server itself as a subprocess. To inspect the tools on their own, use the MCP inspector:

```sh
uv run mcp dev src/telco_ops_agent/server.py
```

## Notes

- The model is set in [agent.py](src/telco_ops_agent/agent.py) and shared by all the agents in `multi.py`.
- The `telco-ops-agent` console script in `pyproject.toml` is still a placeholder that prints a greeting.
- Keep `~/.telco-keys/` out of version control. It lives outside the repo by default.
