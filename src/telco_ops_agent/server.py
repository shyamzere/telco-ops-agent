import json
import os
import re
from pathlib import Path

import snowflake.connector
from cryptography.hazmat.primitives import serialization
from mcp.server.fastmcp import FastMCP

ACCOUNT = "XAFPDTM-VV71865"
USER = "AGENT_SVC"
KEY_PATH = Path(os.environ.get("SNOWFLAKE_KEY_PATH", Path.home() / ".telco-keys" / "agent_key.p8"))
MAX_ROWS = 100
TIMEOUT_SECONDS = 30

# Words that must never appear in a query from the agent (second layer of safety)
BLOCKED = re.compile(
    r"\b(insert|update|delete|drop|alter|create|grant|revoke|merge|truncate|copy|put|get|call|use|set|execute)\b",
    re.IGNORECASE,
)

mcp = FastMCP("telco-ops")


def _connect():
    key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    pkb = key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return snowflake.connector.connect(
        account=ACCOUNT,
        user=USER,
        private_key=pkb,
        role="AGENT_READONLY",
        warehouse="TELCO_WH",
        database="TELCO_DB",
        schema="OPS",
        session_parameters={"STATEMENT_TIMEOUT_IN_SECONDS": TIMEOUT_SECONDS},
    )


def _run(sql: str, params=None) -> str:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        columns = [c[0] for c in cur.description]
        rows = cur.fetchmany(MAX_ROWS + 1)
        truncated = len(rows) > MAX_ROWS
        rows = rows[:MAX_ROWS]
        return json.dumps(
            {
                "columns": columns,
                "rows": [dict(zip(columns, r)) for r in rows],
                "truncated": truncated,
            },
            default=str,
        )
    finally:
        conn.close()


@mcp.tool()
def list_tables() -> str:
    """List the tables available in the telco ops database, with row counts."""
    return _run(
        "SELECT TABLE_NAME, ROW_COUNT FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = 'OPS' ORDER BY TABLE_NAME"
    )


@mcp.tool()
def describe_table(table_name: str) -> str:
    """Show the column names and types of one table."""
    if not re.fullmatch(r"[A-Za-z_]+", table_name):
        return json.dumps({"error": "Invalid table name."})
    return _run(
        "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = 'OPS' AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
        (table_name.upper(),),
    )


@mcp.tool()
def run_query(sql: str) -> str:
    """Run one read-only SELECT query. Returns at most 100 rows."""
    cleaned = sql.strip().rstrip(";").strip()
    if ";" in cleaned:
        return json.dumps({"error": "Only one statement is allowed."})
    if not re.match(r"(?i)^(select|with)\b", cleaned):
        return json.dumps({"error": "Only SELECT queries are allowed."})
    if BLOCKED.search(cleaned):
        return json.dumps({"error": "Query contains a blocked keyword."})
    try:
        return _run(cleaned)
    except Exception as exc:
        return json.dumps({"error": str(exc)[:300]})


if __name__ == "__main__":
    mcp.run()