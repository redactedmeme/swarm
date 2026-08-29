import os

GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
SUB_AGENT_TOKEN = os.getenv("SUB_AGENT_TOKEN", "")
DATA_PROXY_URL  = os.getenv("DATA_PROXY_URL", "")
DATA_PROXY_TOKEN = os.getenv("DATA_PROXY_TOKEN", "")
PORT            = int(os.getenv("PORT", "3000"))

GROQ_BASE_URL   = "https://api.groq.com/openai/v1"
GROQ_MODELS     = ["openai/gpt-oss-20b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
