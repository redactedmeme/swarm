# API Workflow

The Bankr Agent API operates on an asynchronous **submit-poll-complete** pattern.

## Core Operations

**Submit a prompt:**
```bash
curl -X POST "https://api.bankr.bot/agent/prompt" \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is my ETH balance?"}'
```

Returns a job ID in a 202 response for tracking.

**Check job status:**
```bash
curl -X GET "https://api.bankr.bot/agent/job/{jobId}" \
  -H "X-API-Key: YOUR_API_KEY"
```

**Cancel a job:**
```bash
curl -X POST "https://api.bankr.bot/agent/job/{jobId}/cancel" \
  -H "X-API-Key: YOUR_API_KEY"
```

## Job Lifecycle

Jobs progress through states: `pending` → `processing` → `completed` (or `failed`/`cancelled`). Poll every 2 seconds with a 5-minute maximum timeout.

## Key Response Fields

- **jobId & threadId**: For tracking and conversation continuity
- **response**: Natural language output text
- **richData**: Structured data objects (tokens, prices, charts)
- **statusUpdates**: Progress messages during processing
- **processingTime**: Duration in milliseconds

## Authentication & Access

All requests require the `X-API-Key` header. Common errors include 401 (invalid key), 403 (Agent API not enabled), and 429 (rate limiting).

The CLI wrapper (`bankr agent prompt`) automates the entire workflow automatically.
