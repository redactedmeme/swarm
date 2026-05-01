from fastapi import Request, HTTPException
from config import SUB_AGENT_TOKEN


async def verify_token(request: Request):
    if not SUB_AGENT_TOKEN:
        return
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer {SUB_AGENT_TOKEN}":
        raise HTTPException(status_code=401, detail="unauthorized")
