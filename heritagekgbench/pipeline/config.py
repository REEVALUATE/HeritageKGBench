"""Pipeline configuration.

The paper's benchmark runs all used Gemini 2.5 Flash via OpenRouter. Any
LiteLLM-compatible model identifier works; set the corresponding API key in
the environment (e.g. ``OPENROUTER_API_KEY``).
"""

MODEL_ID = "openrouter/google/gemini-2.5-flash"
