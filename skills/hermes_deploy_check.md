# Hermes Deploy Check

## Description
Check the status and recent logs of a Railway service by delegating to Hermes via SwarmInbox.

## When to Use
- User asks "what's the status of X service?"
- User asks to "check logs" or "why is X down?"
- After a deployment, to confirm it succeeded

## Steps
1. Extract service name from instruction
2. Send `status` task_request to Hermes via hermes_dispatch
3. Await result (up to 45s inline, or relay proactively if timeout)
4. Summarize and reply in chan's voice

## Example
Input: "check if the webchat service is running"
Output: delegates `[HERMES: status | check redacted-webchat status and last 20 log lines]`

```python
import asyncio
from typing import Optional

async def skill_hermes_deploy_check(
    service_name: str,
    context: Optional[dict] = None,
) -> dict:
    """
    Check a Railway service's status via Hermes.
    Returns: {"status": str, "msg_id": str | None, "result": str}
    """
    try:
        import hermes_dispatch as hd
        instruction = f"Check {service_name} status and return last 20 log lines"
        msg_id = await hd.send_to_hermes(
            task_type="status",
            instruction=instruction,
            service=service_name,
        )
        if not msg_id:
            return {"status": "error", "msg_id": None, "result": "Hermes unreachable"}

        # Poll for result (up to 45s)
        for _ in range(9):
            await asyncio.sleep(5)
            results = hd.check_results()
            for r in results:
                if r.get("payload", {}).get("reply_to") == msg_id or r.get("id") == msg_id:
                    return {"status": "done", "msg_id": msg_id, "result": str(r.get("result", ""))}

        hd.mark_timed_out(msg_id)
        return {"status": "timeout", "msg_id": msg_id, "result": f"Delegated to Hermes ({msg_id}) — result pending"}
    except Exception as e:
        return {"status": "error", "msg_id": None, "result": str(e)}
```
