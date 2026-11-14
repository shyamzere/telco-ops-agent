import sys

from strands import Agent, tool

from telco_ops_agent.agent import SYSTEM_PROMPT, make_client, model

WRITER_PROMPT = """You write short summaries for a network operations manager.
You receive raw analysis results.
Write 3 sentences at most, in plain English.
Use only the numbers you are given. Never add or change numbers."""

ORCHESTRATOR_PROMPT = """You coordinate two specialists.
For any question about telco incidents or tickets:
1. Call analyst_agent with the question.
2. Call writer_agent with the analyst's full output.
3. Reply with the writer's summary, then the SQL the analyst ran.
For anything else, say you can only help with telco ops data.
Never write SQL yourself and never invent numbers."""


def build(client):
    tools = client.list_tools_sync()
    analyst = Agent(
        model=model, tools=tools, system_prompt=SYSTEM_PROMPT, callback_handler=None
    )
    writer = Agent(model=model, system_prompt=WRITER_PROMPT, callback_handler=None)

    @tool
    def analyst_agent(question: str) -> str:
        """Query the telco database to answer a data question. Returns SQL and results."""
        return str(analyst(question))

    @tool
    def writer_agent(analysis: str) -> str:
        """Turn analysis results into a short summary for a manager."""
        return str(writer(analysis))

    return Agent(
        model=model,
        tools=[analyst_agent, writer_agent],
        system_prompt=ORCHESTRATOR_PROMPT,
    )


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Which region has the most critical incidents?"
    with make_client() as client:
        orchestrator = build(client)
        orchestrator(question)