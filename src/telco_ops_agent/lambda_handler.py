"""AWS Lambda entry point for the single analyst agent.

Invoke with an event like {"question": "Which region has the most critical incidents?"}.
Returns {"answer": "..."}, or {"error": "..."} if the question is missing.
"""

import logging
import os

# Lambda's filesystem is read-only except /tmp. The Snowflake connector writes cache
# files under HOME, so point HOME there before anything else runs. HOME is one of the
# variables the MCP client passes to the server subprocess, so it applies there too.
os.environ["HOME"] = "/tmp"

import boto3  # noqa: E402

from telco_ops_agent.agent import ask  # noqa: E402

logger = logging.getLogger()
logger.setLevel(logging.INFO)

KEY_PARAM = os.environ.get("SNOWFLAKE_KEY_PARAM", "/telco-ops/snowflake-private-key")
KEY_FILE = "/tmp/agent_key.p8"
REGION = os.environ.get("AWS_REGION", "ap-southeast-2")

_key_ready = False  # module state survives between warm invocations


def _ensure_key() -> None:
    """On cold start, fetch the Snowflake private key from SSM and write it to /tmp."""
    global _key_ready
    if _key_ready:
        return
    logger.info("Fetching Snowflake key from SSM parameter %s", KEY_PARAM)
    ssm = boto3.client("ssm", region_name=REGION)
    value = ssm.get_parameter(Name=KEY_PARAM, WithDecryption=True)["Parameter"]["Value"]
    # Create the file with 0600 from the start, so it is never readable by others.
    fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value)
    os.chmod(KEY_FILE, 0o600)  # in case the file already existed with other permissions
    os.environ["SNOWFLAKE_KEY_PATH"] = KEY_FILE
    _key_ready = True
    logger.info("Snowflake key written to %s", KEY_FILE)


def handler(event, context):
    question = event.get("question") if isinstance(event, dict) else None
    if not isinstance(question, str) or not question.strip():
        return {"error": 'Missing "question". Invoke with {"question": "..."}.'}

    try:
        _ensure_key()
        answer = ask(question.strip(), callback_handler=None)
    except Exception as exc:
        logger.error("Agent run failed: %s: %s", type(exc).__name__, exc)
        raise  # let Lambda record this invocation as failed
    return {"answer": answer}
