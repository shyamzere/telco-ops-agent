from strands import Agent
from strands.models import BedrockModel

model = BedrockModel(
    model_id="au.anthropic.claude-haiku-4-5-20251001-v1:0",
    region_name="ap-southeast-2",
)

agent = Agent(
    model=model,
    system_prompt="You are a helpful assistant. Keep answers short.",
)

agent("Say hello and tell me one fact about Auckland.")