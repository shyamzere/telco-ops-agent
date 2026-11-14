import sys
from pathlib import Path

from mcp import StdioServerParameters, stdio_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

SERVER = Path(__file__).parent / "server.py"

model = BedrockModel(
    model_id="au.anthropic.claude-haiku-4-5-20251001-v1:0",
    region_name="ap-southeast-2",
)

SYSTEM_PROMPT = """You are an analyst for a telco network operations team.
Use the tools to answer questions about incidents and support tickets.
Rules:
- If you are unsure about the schema, call list_tables and describe_table first.
- Use run_query for SELECT queries only.
- Base every number on query results. If a query fails, fix it and retry once.
- Never guess. If the data cannot answer the question, say so.
- Show the SQL you ran, then a short plain-English answer.
"""


def make_client() -> MCPClient:
    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(command=sys.executable, args=[str(SERVER)])
        )
    )


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Which region has the most critical incidents?"
    with make_client() as client:
        tools = client.list_tools_sync()
        agent = Agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT)
        agent(question)