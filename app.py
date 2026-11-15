"""Demo web UI for the telco ops agent.

Run with:
    uv sync --group ui
    uv run streamlit run app.py

Config comes from the same places agent.py uses: the standard AWS credential chain
for Bedrock and Lambda, and SNOWFLAKE_KEY_PATH (optional) for the local Snowflake key.
This file adds no secrets of its own.
"""

import json
import logging
import time

import boto3
import streamlit as st
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    ReadTimeoutError,
)

logger = logging.getLogger("telco_ops_app")

REGION = "ap-southeast-2"
FUNCTION_NAME = "telco-ops-agent"
LAMBDA_READ_TIMEOUT = 150  # seconds, longer than the function's 120 s timeout

MODES = {
    "Single agent (local)": (
        "Runs agent.ask() here. The agent starts server.py as an MCP subprocess "
        "and queries Snowflake as AGENT_READONLY."
    ),
    "Multi-agent (local)": (
        "Runs multi.ask() here. An orchestrator calls the analyst agent, then a "
        "writer agent for a short manager summary."
    ),
    "AWS Lambda": (
        f"Invokes the {FUNCTION_NAME} Lambda in {REGION}. It runs the single agent "
        "in AWS, with the Snowflake key from SSM."
    ),
}

EXAMPLES = [
    "How many incidents were opened in the last 7 days?",
    "Which 5 sites had the most critical incidents?",
    "What is the average ticket resolution time by priority?",
    "Delete all closed tickets.",
]


class AgentError(Exception):
    """An error whose message is safe to show to the user as is."""


# ---------- the three paths ----------


def ask_single(question: str) -> str:
    from telco_ops_agent.agent import ask

    return ask(question, callback_handler=None)


def ask_multi(question: str) -> str:
    from telco_ops_agent.multi import ask

    return ask(question, callback_handler=None)


@st.cache_resource
def lambda_client():
    # One attempt only: a retry after a read timeout would run the agent twice.
    config = Config(
        read_timeout=LAMBDA_READ_TIMEOUT,
        retries={"total_max_attempts": 1},
    )
    return boto3.client("lambda", region_name=REGION, config=config)


def ask_lambda(question: str) -> str:
    response = lambda_client().invoke(
        FunctionName=FUNCTION_NAME,
        Payload=json.dumps({"question": question}).encode(),
    )
    if response.get("FunctionError"):
        raise AgentError(
            "The Lambda function failed while answering. "
            f"Check the /aws/lambda/{FUNCTION_NAME} log group in CloudWatch."
        )
    body = json.loads(response["Payload"].read() or b"{}")
    if "error" in body:
        raise AgentError(body["error"])
    if "answer" not in body:
        raise AgentError("The Lambda function returned an unexpected response.")
    return body["answer"]


RUNNERS = {
    "Single agent (local)": ask_single,
    "Multi-agent (local)": ask_multi,
    "AWS Lambda": ask_lambda,
}


def friendly_error(exc: Exception) -> str:
    """Turn an exception into a short message. Never includes a stack trace."""
    if isinstance(exc, AgentError):
        return str(exc)
    if isinstance(exc, NoCredentialsError):
        return "No AWS credentials found. Sign in with the AWS CLI and try again."
    if isinstance(exc, ReadTimeoutError):
        return f"No answer after {LAMBDA_READ_TIMEOUT} s. Try a simpler question."
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "an error")
        return (
            f"AWS returned {code}. Check that your credentials can use "
            f"this service in {REGION}."
        )
    if isinstance(exc, BotoCoreError):
        return "Could not reach AWS. Check your network and credentials."
    return (
        f"Something went wrong ({type(exc).__name__}). "
        "See the terminal running Streamlit for details."
    )


# ---------- page ----------

st.set_page_config(page_title="Telco Ops Agent", page_icon=":material/cell_tower:")

st.title("Telco Ops Agent")
st.caption("Ask plain-English questions about fake telco sites, incidents and tickets.")
st.badge("Read-only", icon=":material/lock:", color="green")

if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.header("Mode")
    mode = st.radio(
        "Where the agent runs",
        list(MODES),
        captions=list(MODES.values()),
        label_visibility="collapsed",
    )

    st.header("Examples")
    clicked = None
    for example in EXAMPLES:
        if st.button(example, width="stretch"):
            clicked = example

    st.divider()
    if st.button("Clear chat", width="stretch"):
        st.session_state.history = []


def show(message: dict) -> None:
    with st.chat_message(message["role"]):
        if message.get("error"):
            st.error(message["content"])
        else:
            st.markdown(message["content"])
        if message["role"] == "assistant":
            st.caption(f"{message['mode']} · {message['seconds']:.1f} s")


for message in st.session_state.history:
    show(message)

typed = st.chat_input("Ask about sites, incidents or tickets")
question = typed or clicked

if question:
    user_message = {"role": "user", "content": question}
    st.session_state.history.append(user_message)
    show(user_message)

    start = time.perf_counter()
    with st.spinner("Asking the agent..."):
        try:
            content, error = RUNNERS[mode](question), False
        except Exception as exc:
            # Log only the type and message to the terminal, not to the page.
            logger.error("Agent run failed: %s: %s", type(exc).__name__, exc)
            content, error = friendly_error(exc), True

    answer = {
        "role": "assistant",
        "content": content,
        "error": error,
        "mode": mode,
        "seconds": time.perf_counter() - start,
    }
    st.session_state.history.append(answer)
    show(answer)
