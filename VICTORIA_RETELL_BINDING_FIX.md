# Retell Dashboard Fix — Phone Number Binding

**STATUS: Manual step required. Kato must do this in the Retell Dashboard.**

## Problem

Phone number `+164****3781` is bound in Retell to the **deprecated** agent `agent_8a326510567e7dc3e2dc5221df` (Victoria v2).

The active agent should be `agent_26e374...` (Victoria v3 / current).

Per Retell behavior, **per-call `agent_id` override is IGNORED by number binding**. Even though `goj_victoria_caller.py` sends `"agent_id": "agent_8a3265..."` in the call payload, Retell routes calls based on the phone number's binding — not the per-call override.

## What Needs Changing

### 1. Log into Retell Dashboard
https://app.retellai.com

### 2. Navigate to Phone Numbers
- Go to **Phone Numbers** in the left sidebar
- Find `+164****3781`

### 3. Change the Agent binding
- Click on the phone number
- Under **Agent**, change from `agent_8a326510567e7dc3e2dc5221df` to `agent_26e374...` (the current active Victoria agent)
- **Save**

### 4. Verify
After saving, place a test call to confirm Victoria answers with the correct voice and prompt.

## Why This Matters
- All outbound Victoria calls are silently routed to the old agent regardless of what the code sends
- The old agent may have stale/incorrect prompts, wrong voice, or outdated DTMF handling
- Until the binding is changed, the caller script has no control over which agent answers

## Script-Side Cleanup (Already Done)
Once Kato rebinds the number in Retell Dashboard, the `AGENT_ID` in `goj_victoria_caller.py` (line 24) should also be updated to match the new agent ID. That is:

```python
AGENT_ID = "agent_26e374..."  # ← update to match Retell Dashboard binding
```

## Date
2026-07-08
