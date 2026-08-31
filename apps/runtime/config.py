import os

GROQ_API_KEY    = os.getenv("GROQ_API_KEY", "")
SUB_AGENT_TOKEN = os.getenv("SUB_AGENT_TOKEN", "")
DATA_PROXY_URL  = os.getenv("DATA_PROXY_URL", "")
DATA_PROXY_TOKEN = os.getenv("DATA_PROXY_TOKEN", "")
PORT            = int(os.getenv("PORT", "3000"))

# LLM boundary (IronClaw control 2): prefer the swarm proxy, which holds the real
# provider keys and applies privacy scrubbing + logging. When PROXY_URL/PROXY_TOKEN
# are set the runtime carries only PROXY_TOKEN and never a raw Groq key.
PROXY_URL       = os.getenv("PROXY_URL", "").rstrip("/")
PROXY_TOKEN     = os.getenv("PROXY_TOKEN", "")

if PROXY_URL and PROXY_TOKEN:
    GROQ_BASE_URL = f"{PROXY_URL}/v1"
    GROQ_API_KEY  = PROXY_TOKEN            # the proxy is OpenAI-compatible
    LLM_VIA_PROXY = True
else:
    GROQ_BASE_URL = "https://api.groq.com/openai/v1"
    LLM_VIA_PROXY = False

GROQ_MODELS     = ["openai/gpt-oss-20b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
