# Fragment 01: Tiered Access Protocol (TAP) for Swarm Services

## Overview
The Tiered Access Protocol (TAP) is a payment-integrated system designed to issue temporary, single-use access tokens for specific swarm services or data retrieval. The payment amount determines the access tier, which correlates with token lifespan, processing priority, and resource allocation.

## Purpose
To provide a mechanism for the swarm to offer differentiated services based on user contribution (payment) while managing resource usage through temporary, consumable access grants. This protocol facilitates micro-settlements (x402) for specific interactions.

## Access Tiers

| Tier Name | Payment Required ([TOKEN]) | Token Lifespan | Processing Priority | Features | Use Case |
|-----------|-----------------------------|----------------|---------------------|----------|----------|
| **Basic Access** | 0.01 | 1 hour | Low | Standard processing, basic data | Exploring basic swarm functions. |
| **Enhanced Access** | 0.05 | 6 hours | Medium | Higher priority, bundled data access | Deeper interaction or requesting complex outputs. |
| **Premium Access** | 0.10 | 24 hours | High | Highest priority, persistent logging, premium resources | Critical or high-value interactions requiring reliability. |

## Technical Mechanism

### 1. Request Initiation
- Client makes an API request specifying the desired tier: `POST /swarm/tap/request_access`
- Request body includes:
  - `tier`: (string, required) One of `basic`, `enhanced`, `premium`.
  - `payment_proof`: (object, required) Contains details like transaction signature, amount, and sender address, conforming to x402 standards.

### 2. Payment Validation
- The system invokes the `validate_payment` function (as defined in `committeerituals/x402_sigil_scarifier.py`).
- The function checks if the `payment_proof.amount` meets the minimum requirement for the requested `tier`.
- If validation fails, the system returns an HTTP 400 error with details.

### 3. Token Generation
- On successful validation, the system generates a unique, single-use access token string using a cryptographically secure random generator (e.g., `secrets.token_urlsafe`).
- The token's metadata (tier, lifespan, associated payer) is stored in a volatile cache/database (`_token_cache` in the code).
- A unique `token_id` is derived (e.g., SHA256 hash of seed and payer info).

### 4. Response Delivery
- The generated access token (or a reference like `token_id`) is returned to the client in the API response body.

### 5. Token Consumption & Expiry
- When the client uses the token for its intended purpose (e.g., `POST /swarm/tap/use_token`), the system retrieves the token from the cache.
- If the token's `is_consumed` flag is already `True`, the request fails.
- Otherwise, the system marks the token as `is_consumed = True` and proceeds with fulfilling the request.
- The token is automatically purged from the cache after its `lifespan` expires, regardless of whether it was consumed.

### 6. Error Handling
- Attempting to use an already consumed token returns: `{"error": "Access token expired or already used."}`
- Attempting to use a non-existent token returns: `{"error": "Access token not found."}`

### 7. Resource Cycling
- Successfully validated payments contribute to a designated swarm liquidity pool, supporting ongoing operations.

## Integration Points
- **x402 Standard:** Payment validation relies on standard transaction proof formats.
- **Async Settlement Handler:** Successful validation triggers the `process_settlement` function (in `x402_sigil_scarifier.py`) for background processing and logging.

## Governance & Future Components
- **Sevenfold Committee:** Envisioned as a future decentralized governance body responsible for setting tier parameters (prices, lifespans) and overseeing protocol changes. Currently, parameters are defined statically in `TIER_CONFIGS`.
- **OuroborosSettlement:** Envisioned as a future advanced settlement engine for handling complex payment routing, batch processing, and integration with external DeFi protocols. Currently simulated by `process_settlement`.

## Example Flow
1. Client sends `POST /swarm/tap/request_access` with `{ "tier": "enhanced", "payment_proof": {...} }`.
2. System validates proof (requires >= 0.05 [TOKEN]).
3. System generates token `TKN_clientabc_123def...`, stores it with metadata, sets expiry.
4. System returns token to client.
5. Client later sends `POST /swarm/tap/use_token` with `{ "token": "TKN_clientabc_123def..." }`.
6. System finds token, checks `is_consumed` (False), sets `is_consumed` to True, fulfills request.
7. If unused, token automatically expires and is deleted after 6 hours.
