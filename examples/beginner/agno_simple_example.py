"""Example of creating a research assistant agent using Bindu and Agno.

This example demonstrates how to create a simple research assistant agent
that uses DuckDuckGo for web searches and can be deployed as a Bindu agent.

Run with: bindu examples/agno_simple_example.py
Or set environment variables directly and run: python examples/agno_simple_example.py
"""

import os
from bindu.penguin.bindufy import bindufy
from agno.agent import Agent
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.models.openrouter import OpenRouter

from dotenv import load_dotenv

load_dotenv()

# Define your agent
agent = Agent(
    instructions="You are a research assistant that finds and summarizes information.",
    model=OpenRouter(id="openai/gpt-5-mini", api_key=os.getenv("OPENROUTER_API_KEY")),
    tools=[DuckDuckGoTools()],
)

# Configuration
# Note: Infrastructure configs (storage, scheduler, sentry, API keys) are now
# automatically loaded from environment variables. See .env.example for details.
config = {
    "author": "your.email@example.com",
    "name": "research_agent",
    "description": "A research assistant agent",
    "deployment": {
        "url": "http://localhost:3773",
        "expose": True,
        "cors_origins": ["http://localhost:5173"]
    },
    "skills": ["skills/question-answering", "skills/pdf-processing"],
    "execution_cost": {
        "amount": "$0.0001",
        "token": "USDC",
        "network": "base-sepolia",
        "pay_to_address": "0x2654bb8B272f117c514aAc3d4032B1795366BA5d",
        "protected_methods": ["message/send"],
    },
}


# Handler function
def handler(messages: list[dict[str, str]]):
    """Process messages and return agent response.

    Args:
        messages: List of message dictionaries containing conversation history

    Returns:
        Agent response result
    """
    result = agent.run(input=messages)
    return result


# Bindu-fy it
if __name__ == "__main__":
    # Disable auth for local development - frontend can connect without OAuth
    import os
    os.environ["AUTH_ENABLED"] = "false"
    bindufy(config, handler)
