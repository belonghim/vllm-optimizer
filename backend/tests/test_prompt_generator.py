from models.load_test import SyntheticPromptConfig
from services.prompt_generator import generate_prompt


def test_returns_string():
    config = SyntheticPromptConfig(distribution="uniform", min_tokens=50, max_tokens=100)
    result = generate_prompt(config)
    assert isinstance(result, str)
    assert len(result) > 0


def test_uniform_generates_varied_prompts():
    config = SyntheticPromptConfig(distribution="uniform", min_tokens=50, max_tokens=200)
    prompts = [generate_prompt(config) for _ in range(10)]

    assert all(isinstance(p, str) for p in prompts)

    lengths = [len(p) for p in prompts]
    assert len(set(lengths)) > 1

    min_expected = 50 * 4
    max_expected = 200 * 4
    tolerance = 50

    for length in lengths:
        assert length >= (min_expected - tolerance)
        assert length <= (max_expected + tolerance)


def test_normal_generates_around_mean():
    mean = 100
    config = SyntheticPromptConfig(
        distribution="normal", min_tokens=50, max_tokens=150, mean_tokens=mean, stddev_tokens=10
    )

    prompts = [generate_prompt(config) for _ in range(20)]
    assert all(isinstance(p, str) for p in prompts)

    token_counts = [len(p) / 4.0 for p in prompts]
    avg_tokens = sum(token_counts) / len(token_counts)

    tolerance = mean * 0.5
    assert abs(avg_tokens - mean) <= tolerance


def test_uniform_length_in_bounds():
    min_tokens = 10
    max_tokens = 20
    config = SyntheticPromptConfig(distribution="uniform", min_tokens=min_tokens, max_tokens=max_tokens)

    for _ in range(10):
        prompt = generate_prompt(config)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

        min_chars = min_tokens * 4
        max_chars = max_tokens * 4
        tolerance = 20
        actual_length = len(prompt)

        assert actual_length >= (min_chars - tolerance)
        assert actual_length <= (max_chars + tolerance)
