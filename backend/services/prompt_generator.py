"""
Synthetic prompt generator for load testing.
Generates prompts of approximate token length using character-based estimation (~4 chars/token).
No external dependencies — uses only Python stdlib.
"""

import random
from models.load_test import SyntheticPromptConfig

_WORD_POOL = [
    "explain",
    "describe",
    "analyze",
    "compare",
    "summarize",
    "discuss",
    "evaluate",
    "define",
    "list",
    "provide",
    "how",
    "what",
    "why",
    "when",
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "system",
    "process",
    "function",
    "method",
    "result",
    "output",
    "input",
    "data",
    "model",
    "network",
    "layer",
    "parameter",
    "configuration",
    "performance",
    "optimization",
    "efficiency",
    "accuracy",
    "latency",
    "request",
    "response",
    "server",
    "client",
    "endpoint",
    "service",
    "machine",
    "learning",
    "artificial",
    "intelligence",
    "neural",
    "deep",
    "language",
    "natural",
    "processing",
    "generation",
    "inference",
    "compute",
    "memory",
    "storage",
    "bandwidth",
    "throughput",
    "capacity",
]

_CHARS_PER_TOKEN = 4  # Approximation: ~4 characters per token for English text


def generate_prompt(config: SyntheticPromptConfig) -> str:
    """
    Generate a synthetic prompt with approximate target token length.

    Args:
        config: SyntheticPromptConfig with distribution params

    Returns:
        Generated prompt string
    """
    if config.distribution == "normal":
        mean = config.mean_tokens or (config.min_tokens + config.max_tokens) // 2
        stddev = config.stddev_tokens or max(1, (config.max_tokens - config.min_tokens) // 6)
        target_tokens = random.gauss(mean, stddev)
        target_tokens = max(config.min_tokens, min(config.max_tokens, target_tokens))
    else:
        target_tokens = random.randint(config.min_tokens, config.max_tokens)

    target_chars = int(target_tokens * _CHARS_PER_TOKEN)

    words = []
    current_len = 0
    while current_len < target_chars:
        word = random.choice(_WORD_POOL)
        words.append(word)
        current_len += len(word) + 1  # +1 for space

    return " ".join(words)
