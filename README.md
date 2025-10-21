# Mistral Router

> A lightweight, high-performance FastAPI gateway that intelligently routes requests to the most appropriate Mistral AI model (`small` vs. `medium`), optimizing for **cost, latency, and capability**.

This service acts as a smart proxy: it analyzes each request and chooses the right model for the job. It provides automatic fallbacks, cost and latency tracking, and a Prometheus-compatible metrics endpoint.

## Quick Start

### 1. Clone and Install

```bash
git clone https://github.com/jathurchan/mistral-router.git
cd mistral-router
pip install -r requirements.txt
```

### 2. Environment Configuration

```bash
# Required
export MISTRAL_API_KEY="your_api_key_here"

# Optional
export ROUTER_LENGTH_THRESHOLD=120  # Prompts shorter than this use 'small'
export ROUTER_CLIENT_TIMEOUT_S=15
export ROUTER_MAX_INPUT_TOKENS=4096
```

### 3. Run

```bash
# For development (with hot-reload)
uvicorn app.main:app --reload

# Or with Docker
docker build -t mistral-router .
docker run -p 8000:8000 -e MISTRAL_API_KEY=$MISTRAL_API_KEY mistral-router
```

The service is now running at `http://localhost:8000`.

## API Usage & Demo

The router mimics the official Mistral API. Use it as a drop-in replacement by setting `"model": "auto"` to enable intelligent routing.

### Example 1: Simple Request → `small`

A short prompt is automatically routed to `mistral-small-latest` for low latency and cost. The router's decision is returned in the response headers.

```bash
curl -i -X POST http://localhost:8000/v1/chat/completions \
 -H "Content-Type: application/json" \
 -H "Authorization: Bearer $MISTRAL_API_KEY" \
 -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "What is the capital of France?"}]
 }'
```

**Response Headers:**

```plaintext
HTTP/1.1 200 OK
X-Router-Model: mistral-small-latest
X-Router-Latency-MS: 112
X-Router-Cost-USD: 0.0000056
...
```

(Response body is the standard Mistral API completion JSON)

### Example 2: Complex Request → `medium`

A request using `tools` (function calling) is automatically upgraded to `mistral-medium-latest`.

Bash

```bash
curl -i -X POST http://localhost:8000/v1/chat/completions \
 -H "Content-Type: application/json" \
 -H "Authorization: Bearer $MISTRAL_API_KEY" \
 -d '{
    "model": "auto",
    "messages": [{"role": "user", "content": "Extract user info from text..."}],
    "tools": [ ... ]
 }'
```

**Response Headers:**

```bash
HTTP/1.1 200 OK
X-Router-Model: mistral-medium-latest
X-Router-Latency-MS: 322
X-Router-Cost-USD: 0.0001520
...
```

### Example 3: Metrics

A Prometheus-compatible metrics endpoint is exposed for monitoring.

```bash
curl http://localhost:8000/metrics
```

**Output:**

```plaintext
# HELP router_requests_total Total number of requests
router_requests_total{model="mistral-small-latest",status_code="200"} 1.0
router_requests_total{model="mistral-medium-latest",status_code="200"} 1.0
# HELP router_fallback_total Total fallbacks from small to medium
router_fallback_total{from="small",to="medium"} 0.0
...
```

## Problem & Solution

### The Problem

Defaulting to a single large model (e.g., `mistral-medium-latest`) for all requests is simple but inefficient. This approach is:

- **Costly:** Simple prompts are billed at the same high rate as complex ones.
- **Slow:** Users wait longer than necessary for simple answers.
- **Brittle:** A single model failure or a low-quality response fails the entire request.

Cost Comparison (200 tokens in / 200 tokens out)

| **Model**               | **Cost per turn** | **1M turns** | **5M turns** |
| ----------------------- | ----------------- | ------------ | ------------ |
| `mistral-small-latest`  | $0.00008          | $80          | $400         |
| `mistral-medium-latest` | $0.00048          | $480         | $2,400       |

This router provides a **6x cost-saving** potential on simple queries.

### The Solution

This service acts as an intelligent proxy that provides:

- **Dynamic Routing:** Uses prompt length and capability requirements (e.g., `tools`) to select the most cost-effective model.
- **Automatic Fallback:** If `small` fails or returns a low-quality response, the router automatically retries the request with `medium`.
- **Full Visibility:** Injects `X-Router-*` headers with cost, latency, and model choice. Exposes a `/metrics` endpoint.
- **Manual Override:** A user can always bypass routing and force a specific model (e.g., `"model": "mistral-medium-latest"`).

## Architecture

```plaintext
┌─────────────┐      ┌─────────────────┐      ┌─────────────────────┐
│   Client    │ ───▶ │ FastAPI Gateway │ ───▶ │    Routing Logic    │
│  (uses SDK) │      │ (localhost:8000)│      │ 1. Length?          │
└─────────────┘      └─────────────────┘      │ 2. Capabilities?    │
                                              │ 3. Fallback?        │
                                              └─────┬───────────────┘
                                                    │
                                 ┌──────────────--──┴─────────────────┐
                                 │                                    │
                                 ▼                                    ▼
                       ┌──────────────────────┐               ┌───────────────────────┐
                       │ mistral-small-latest │               │ mistral-medium-latest │
                       └──────────────────────┘               └───────────────────────┘
```

- **FastAPI Gateway:** A single `/v1/chat/completions` endpoint proxies the official Mistral API.
- **Routing Logic:** A simple rules engine checks each request:
  - Is `tools` (function calling) present? → Use `medium`.
  - Is prompt length > `ROUTER_LENGTH_THRESHOLD`? → Use `medium`.
  - Default → Use `small`.
- **Fallback Handler:** If the `small` model fails or its response is flagged as low-quality (e.g., empty), the logic transparently retries the request on `medium`.
- **Metrics:** A `Prometheus`-compatible collector tracks counters and histograms for all requests, fallbacks, and costs.

## Testing & Evaluation

### Unit Tests

A full `pytest` suite covers all routing logic, fallback behavior, metadata injection, policy overrides, and metrics.

```bash
pytest
```

### Evaluation Script

An offline script (`eval.py`) runs a sample dataset through the router vs. an "always-medium" baseline to demonstrate real-world savings.

```bash
python eval.py
```

**Sample Output:**

| **policy**    | **model**             | **tokens_in** | **tokens_out** | **latency_ms** | **cost_usd** | **reason**      |
| ------------- | --------------------- | ------------- | -------------- | -------------- | ------------ | --------------- |
| router        | mistral-small-latest  | 11            | 15             | `[TBD]`        | `[TBD]`      | simple          |
| router        | mistral-medium-latest | 210           | 34             | `[TBD]`        | `[TBD]`      | requires: tools |
| always-medium | mistral-medium-latest | 11            | 15             | `[TBD]`        | `[TBD]`      | baseline        |
| always-medium | mistral-medium-latest | 210           | 34             | `[TBD]`        | `[TBD]`      | baseline        |

**Results:**

- **Router Cost:** `[TBD]`
- **Baseline Cost:** `[TBD]`
- **Savings:** `[TBD]`
- **Avg. Latency:** Router: `[TBD]` | Baseline: `[TBD]`

## Future Work

- **ML-based Routing:** Train a small classifier to predict prompt "difficulty" for more nuanced routing.
- **Budget Policies:** Allow users to set per-API-key budgets or SLOs (e.g., "prefer_cost" vs. "prefer_latency").
- **Dashboard:** A simple Streamlit/Gradio UI to visualize the `/metrics` data.
- **Shadow Routing:** Send requests to both models in parallel to A/B test routing logic without impacting users.

## Author

Jathurchan Selvakumar
