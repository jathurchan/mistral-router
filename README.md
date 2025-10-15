# `llm-mux` - Framework for Cost-Efficient LLM Applications

> llm-mux is a lightweight FastAPI framework for cost-efficient LLM applications — plug in your Mistral API key and get a routing gateway in under 60 seconds.
> By default, it uses Mistral models for tiered routing, but the architecture is provider-agnostic and can be extended to other backends.

A production-ready LLM routing framework that minimizes cost, reduces latency, and provides built-in observability.

## Motivation

Building a quick prototype with an LLM is easy. Building a **scalable, cost-efficient, and observable production system** is not.

Most teams repeatedly:

- **Reinvent the wheel** — re-implement routing, tracking, and APIs for every new project.
- **Fly blind** — ship without cost, latency, or usage visibility.
- **Burn budget** — use large models for trivial queries.

**llm-mux** solves these problems once — giving developers a clean, extensible **framework** that works from day one.

## Key Features

- **Intelligent Tiered Routing** – Automatically routes queries between small and large LLMs based on complexity, reducing both cost and latency.
- **Cost Optimization** – Achieves up to **`[TBD]`**% cost savings with negligible impact on response quality.
- **Built-in Observability** – Exposes real-time metrics for cost, latency, token usage, and routing decisions through a simple API.
- **Extensible Framework** – Easily add endpoints, integrate new providers, or customize routing rules and caching strategies.
- **Docker-First** – Runs locally or in production with a single `docker-compose up` command.
- **Fast Developer Onboarding** – Minimal setup: clone the repo, set an API key, and start building.
- **Pluggable Middleware** – Supports authentication, rate limiting, logging, and other middleware extensions.
- **Provider-Agnostic** – Optimized for Mistral but adaptable to OpenAI, Anthropic, vLLM, or custom backends.
- **Robust Test Coverage** – Over **`[TBD]`**% coverage across core routing and tracking modules.

## Quick Start

### Docker (Recommended)

```bash
git clone https://github.com/jathurchan/llm-mux.git
cd llm-mux
cp .env.example .env   # Add your MISTRAL_API_KEY
docker-compose up --build
```

- Service available at [http://localhost:8000](http://localhost:8000)
- API docs at [http://localhost:8000/docs](http://localhost:8000/docs)

### Local Python Run

```bash
pip install -r requirements.txt
export MISTRAL_API_KEY="your_api_key_here"
python demo.py
```

## Architecture

```plaintext
   Client
    │
    ▼
┌───────────────┐
│ FastAPI       │   main.py
│ Gateway       │
└───┬───────────┘
    │
    ▼
┌───────────────┐
│ Complexity    │   src/router.py
│ Router        │───► routes query to model tier
└───┬───────────┘
    │
    ├────────► mistral-small-latest  (fast & cheap)
    │
    └────────► mistral-large-latest  (powerful & costly)
    ▼
┌───────────────┐
│ Metrics       │   src/tracker.py
│ Tracker       │───► cost, latency, tokens, usage
└───────────────┘
```

| **Component**         | **Role**                                                                            |
| --------------------- | ----------------------------------------------------------------------------------- |
| FastAPI Gateway       | Receives and validates incoming requests; exposes `/query` and `/metrics` endpoints |
| Complexity Router     | Scores incoming queries and decides the optimal model tier                          |
| Metrics Tracker       | Logs cost, latency, token usage, and routing decisions                              |
| SDK-Ready Integration | Easy to extend, plug in other providers or caching layers                           |
| Docker Compose        | Ensures consistent and fast deployment locally and in production                    |

## Project Structure

```plaintext
llm-mux/
├── src/
│   ├── router.py          # Complexity scoring and model tier routing logic
│   ├── tracker.py         # Cost, latency, and usage tracking
│   ├── models.py          # Pydantic schemas for requests and responses
│   ├── mistral_client.py  # Wrapper for Mistral API calls
│   └── __init__.py
│
├── tests/
│   ├── test_router.py     # Unit tests for routing logic
│   ├── test_tracker.py    # Unit tests for metrics tracking
│   ├── test_client.py     # Tests for Mistral client wrapper
│   └── __init__.py
│
├── main.py                # FastAPI entrypoint (gateway layer)
├── demo.py                # Simple demo runner with example queries
├── requirements.txt       # Python dependencies
├── requirements-dev.txt   # Dev/test dependencies
├── dockerfile             # Docker image definition
├── docker-compose.yml     # One-command local deployment
├── .env.example           # Example environment variables (Mistral API key)
├── .gitignore
└── README.md
```

## Demo Results

| **Metric**           | **Always-Large Baseline** | **llm-mux (Smart Routing)** | **Improvement** |
| -------------------- | ------------------------- | --------------------------- | --------------- |
| Total Cost (10k req) | [TBD]                     | [TBD]                       | [TBD]           |
| P50 Latency          | [TBD]                     | [TBD]                       | [TBD]           |
| P95 Latency          | [TBD]                     | [TBD]                       | [TBD]           |
| Small Model Usage    | [TBD]                     | [TBD]                       | —               |
| Avg. Quality Score*  | [TBD]                     | [TBD]                       | [TBD]           |

## API Reference

### `POST /query`

Submits a query to the routing gateway.

**Request:**

```json
{"query": "Compare and contrast monoliths vs. microservices"}
```

**Response:**

```json
{
  "answer": "...",
  "routing_decision": "Routed to LARGE (score: 0.90)",
  "model_used": "mistral-large-latest",
  "metrics": {
    "latency_ms": 1421,
    "tokens_in": 8,
    "tokens_out": 210,
    "cost_usd": 0.002552
  }
}
```

### `GET /metrics`

Retrieves cumulative usage, cost, and performance statistics.

**Response:**

```json
{
  "total_requests": 152,
  "total_cost": "$0.24",
  "avg_latency_ms": 845,
  "cost_savings_vs_always_large": "71.8%",
  "small_model_usage_percent": "76.3%",
  "model_breakdown": {
    "mistral-small-latest": 116,
    "mistral-large-latest": 36
  }
}
```

## Extending llm-mux

| **Use Case**                  | **How to Extend**                              |
| ----------------------------- | ---------------------------------------------- |
| Add new routing rules         | Modify `src/router.py`                         |
| Add endpoints                 | Extend `main.py` or add new routers            |
| Add caching                   | Wrap responses with Redis or in-memory caching |
| Add auth                      | Integrate FastAPI middleware                   |
| Use another provider          | Swap out model client in `router.py`           |
| Integrate observability stack | Plug Prometheus / Grafana via metrics endpoint |

## Testing

```bash
pip install -r requirements-dev.txt
pytest --cov=src tests/
```

| **Module** | **Coverage** |
| ---------- | ------------ |
| router.py  | `[TBD]`      |
| tracker.py | `[TBD]`      |
| Overall    | `[TBD]`      |

## FAQ: Design Decisions and Tradeoffs

### Why use FastAPI for the gateway?

FastAPI provides an async-native, high-performance API layer with strong typing and auto-generated documentation.

- It allows rapid iteration on routing logic and API endpoints.
- The contract between client apps and the backend is explicit and easy to maintain.
- Middleware such as authentication or rate limiting can be added with minimal effort.

    **Tradeoff:** For more advanced use cases (e.g., high-throughput streaming), you’d need additional components or a worker layer.

### Why is the project Docker-first?

Because reviewers or new contributors should be able to clone and run the project **in one command** — no environment issues, no hidden setup steps.

- Ensures identical behavior across local and test environments.
- Makes it easy to run in interviews, hackathons, or early production settings.

    **Tradeoff:** Slightly larger image size and slower build than a bare-metal setup.

### Why start with heuristic routing instead of an ML model?

Rule-based routing is **fast**, transparent, and good enough to demonstrate cost-aware orchestration.

- Sub-millisecond routing decisions.
- Easy to debug and reason about.
- Clear upgrade path toward learned routing if needed.

    **Tradeoff:** Heuristics don’t adapt automatically to changing query patterns and may misroute edge cases.

### Why make the architecture provider-agnostic?

Even though the framework is designed around Mistral models, it intentionally doesn’t lock into a single provider.

- Mistral remains the default, but other APIs (e.g., OpenAI, vLLM) can be plugged in easily.
- Protects against vendor lock-in and allows comparison or fallback strategies.

    **Tradeoff:** Maintaining a clean abstraction layer adds slight complexity.

### Why position llm-mux as a framework, not just a project?

Most teams repeatedly build the same backend foundation for LLM apps — routing, tracking, metrics, and auth. This project solves that once.

- Faster prototyping and onboarding.
- Clean extension points for product-specific logic.
- Provides a minimal, production-ready baseline out of the box.

    **Tradeoff:** Some teams will still need to customize components to match their product or infrastructure.

## Future Directions

- ML-based routing model
- Request caching layer
- More routing tiers (tiny / large / specialized)
- Integration with RAG pipelines
- Streaming support

## License & Author

**License:** MIT License — free to use and modify.

**Author:** Jathurchan Selvakumar
