"""Mock LLM shared across the lab projects."""
import random
import time


MOCK_RESPONSES = {
    "default": [
        "This is a mock AI response. In production this would come from OpenAI or Anthropic.",
        "The agent is running correctly. Ask another question to continue the conversation.",
        "Your request was processed successfully by the production-ready AI agent.",
    ],
    "docker": [
        "Containers package an app so it can run the same way everywhere: build once, run anywhere."
    ],
    "deploy": [
        "Deployment is the process of moving code from your machine to a server so other users can access it."
    ],
    "health": ["The agent is healthy and all monitored systems are operational."],
}


def ask(question: str, delay: float = 0.1) -> str:
    time.sleep(delay + random.uniform(0, 0.05))

    question_lower = question.lower()
    for keyword, responses in MOCK_RESPONSES.items():
        if keyword in question_lower:
            return random.choice(responses)

    return random.choice(MOCK_RESPONSES["default"])


def ask_stream(question: str):
    response = ask(question)
    for word in response.split():
        time.sleep(0.05)
        yield word + " "