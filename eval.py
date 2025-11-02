"""
Evaluation script for Mistral Router.

Compares router performance (using "model": "auto") against a baseline
(always using the medium model) to validate cost savings and routing accuracy.

Usage:
  export MISTRAL_API_KEY="your_key_here"
  python eval.py
"""

import asyncio
import httpx
import os
import json
import sys
from typing import List, Dict, Any, Tuple
from datetime import datetime

# Timeout for the HTTP client during evaluation
EVAL_CLIENT_TIMEOUT_S = 75
# Delay between requests to avoid rate limiting
REQUEST_DELAY_S = 10

EVAL_MAX_RETRIES = 5
EVAL_RETRY_DELAY_S = 10
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}

TEST_PROMPTS = [
    # Simple queries (should route to small)
    {
        "messages": [{"role": "user", "content": "What is the capital of France?"}],
        "expected_model": "small",
        "category": "simple_factual",
    },
    {
        "messages": [{"role": "user", "content": "Who won the 2018 World Cup?"}],
        "expected_model": "small",
        "category": "simple_factual",
    },
    {
        "messages": [{"role": "user", "content": "What is 15 * 12?"}],
        "expected_model": "small",
        "category": "simple_math",
    },
    {
        "messages": [{"role": "user", "content": "Hi, how are you?"}],
        "expected_model": "small",
        "category": "casual",
    },
    {
        "messages": [{"role": "user", "content": "Define photosynthesis"}],
        "expected_model": "small",
        "category": "simple_definition",
    },
    {
        "messages": [{"role": "user", "content": "Name three colors"}],
        "expected_model": "small",
        "category": "simple_list",
    },
    {
        "messages": [
            {"role": "user", "content": "What year did the moon landing happen?"}
        ],
        "expected_model": "small",
        "category": "simple_factual",
    },
    {
        "messages": [{"role": "user", "content": "Spell 'restaurant'"}],
        "expected_model": "small",
        "category": "simple_task",
    },
    {
        "messages": [{"role": "user", "content": "Is Sigriswil in Switzerland?"}],
        "expected_model": "small",
        "category": "simple_yes_no",
    },
    {
        "messages": [{"role": "user", "content": "Convert 100 USD to EUR"}],
        "expected_model": "small",
        "category": "simple_conversion",
    },
    # Complex queries (should route to medium)
    {
        "messages": [
            {
                "role": "user",
                "content": "Analyze the pros and cons of renewable energy sources compared to fossil fuels, considering economic, environmental, and social factors.",
            }
        ],
        "expected_model": "medium",
        "category": "complex_analysis",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": "Explain in detail how machine learning algorithms work, including examples of supervised and unsupervised learning.",
            }
        ],
        "expected_model": "medium",
        "category": "complex_explanation",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": "Compare and contrast the political systems of democracy and authoritarianism, with historical examples.",
            }
        ],
        "expected_model": "medium",
        "category": "complex_comparison",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": "Derive the quadratic formula from first principles and explain each step of the mathematical reasoning.",
            }
        ],
        "expected_model": "medium",
        "category": "complex_derivation",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": "Evaluate the effectiveness of different psychological therapies for treating anxiety disorders, citing research evidence.",
            }
        ],
        "expected_model": "medium",
        "category": "complex_evaluation",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": "Provide a comprehensive overview of quantum computing, including the principles of quantum mechanics it relies on, current challenges, and potential applications.",
            }
        ],
        "expected_model": "medium",
        "category": "complex_comprehensive",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": "Critique the arguments for and against universal basic income, considering economic theory, empirical evidence, and ethical considerations.",
            }
        ],
        "expected_model": "medium",
        "category": "complex_critique",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": "Develop a detailed strategic plan for a small business entering the e-commerce market, including market analysis, competitive positioning, and risk assessment.",
            }
        ],
        "expected_model": "medium",
        "category": "complex_strategy",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": "Assess the long-term implications of artificial intelligence on the job market, considering different sectors, skill levels, and potential policy responses.",
            }
        ],
        "expected_model": "medium",
        "category": "complex_assessment",
    },
    {
        "messages": [
            {
                "role": "user",
                "content": "Justify your position on whether genetic engineering of humans should be permitted, addressing scientific, ethical, and societal dimensions.",
            }
        ],
        "expected_model": "medium",
        "category": "complex_justification",
    },
]

class RouterEvaluator:
    """Runs a set of prompts against the router and a baseline policy."""

    def __init__(
        self,
        router_url: str,
        api_key: str,
        model_small: str,
        model_medium: str,
    ):
        self.router_url = router_url.rstrip("/")
        self.api_key = api_key
        self.model_small_name = model_small
        self.model_medium_name = model_medium
        self.headers = {"Authorization": f"Bearer {self.api_key}"}
        self.client = httpx.AsyncClient(timeout=EVAL_CLIENT_TIMEOUT_S)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def _run_request(
        self, model_name: str, messages: List[Dict[str, str]]
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Helper to run a single request and return (response_json, headers_dict)."""
        last_exception = None

        for attempt in range(EVAL_MAX_RETRIES):
            try:
                response = await self.client.post(
                    f"{self.router_url}/v1/chat/completions",
                    json={"model": model_name, "messages": messages},
                    headers=self.headers,
                )
                response.raise_for_status()  # Raise on 4xx/5xx errors
                return response.json(), response.headers

            except httpx.HTTPStatusError as e:
                last_exception = e
                if e.response.status_code in RETRYABLE_STATUS_CODES:
                    print(
                        f"    └─ Retrying... (Attempt {attempt + 1}/{EVAL_MAX_RETRIES}) "
                        f"Received {e.response.status_code}. Waiting {EVAL_RETRY_DELAY_S}s."
                    )
                    await asyncio.sleep(EVAL_RETRY_DELAY_S)
                else:
                    # Don't retry on 400, 401, 404, etc.
                    raise e

            except httpx.RequestError as e:
                last_exception = e
                print(
                    f"    └─ Retrying... (Attempt {attempt + 1}/{EVAL_MAX_RETRIES}) "
                    f"Network error: {e}. Waiting {EVAL_RETRY_DELAY_S}s."
                )
                await asyncio.sleep(EVAL_RETRY_DELAY_S)

        raise last_exception  # type: ignore

    async def test_router(self, prompt: Dict[str, Any]) -> Dict[str, Any]:
        """Test a prompt with the router ("auto" mode)."""
        data, headers = await self._run_request("auto", prompt["messages"])

        return {
            "policy": "router",
            "model_logical": headers.get("X-Router-Model-Logical", "unknown"),
            "model_actual": headers.get("X-Router-Model", "unknown"),
            "reason": headers.get("X-Router-Reason", "unknown"),
            "fallback": headers.get("X-Router-Fallback", "false") == "true",
            "latency_ms": float(headers.get("X-Router-Latency-MS", 0)),
            "cost_usd": float(headers.get("X-Router-Cost-USD", 0)),
            "tokens_in": data.get("usage", {}).get("prompt_tokens", 0),
            "tokens_out": data.get("usage", {}).get("completion_tokens", 0),
            "category": prompt.get("category", "unknown"),
            "expected_model": prompt.get("expected_model", "unknown"),
        }

    async def test_baseline(self, prompt: Dict[str, Any]) -> Dict[str, Any]:
        """Test a prompt with baseline (always medium)."""
        data, headers = await self._run_request(
            self.model_medium_name, prompt["messages"]
        )

        return {
            "policy": "always-medium",
            "model_logical": headers.get(
                "X-Router-Model-Logical", self.model_medium_name
            ),
            "model_actual": headers.get("X-Router-Model", self.model_medium_name),
            "reason": headers.get("X-Router-Reason", "manual_override"),
            "fallback": False,  # Fallback shouldn't happen on explicit medium
            "latency_ms": float(headers.get("X-Router-Latency-MS", 0)),
            "cost_usd": float(headers.get("X-Router-Cost-USD", 0)),
            "tokens_in": data.get("usage", {}).get("prompt_tokens", 0),
            "tokens_out": data.get("usage", {}).get("completion_tokens", 0),
            "category": prompt.get("category", "unknown"),
            "expected_model": prompt.get("expected_model", "unknown"),
        }

    async def run_evaluation(self) -> Dict[str, Any]:
        """
        Run the full evaluation for all test prompts.

        Compares "auto" vs "always-medium" for each prompt and analyzes
        the aggregated results.
        """
        print(f"Starting Router Evaluation on {self.router_url}...")
        print(f"Testing {len(TEST_PROMPTS)} prompts (Router vs. Baseline)\n")

        results = []
        num_errors = 0

        for i, prompt in enumerate(TEST_PROMPTS, 1):
            print(f"[{i}/{len(TEST_PROMPTS)}] Testing Category: {prompt['category']}")

            try:
                router_result = await self.test_router(prompt)
                results.append(router_result)
                print(
                    f"  Router:   {router_result['model_actual']} (${router_result['cost_usd']:.8f}) "
                    f"Reason: {router_result['reason']}"
                )
            except Exception as e:
                print(f"  Router Error: {e}")
                num_errors += 1

            await asyncio.sleep(REQUEST_DELAY_S)

            try:
                baseline_result = await self.test_baseline(prompt)
                results.append(baseline_result)
                print(
                    f"  Baseline: {baseline_result['model_actual']} (${baseline_result['cost_usd']:.8f})"
                )
            except Exception as e:
                print(f"  Baseline Error: {e}")
                num_errors += 1

            print("-" * 20)
            await asyncio.sleep(REQUEST_DELAY_S)  # Avoid rate limiting

        return self._analyze_results(results, num_errors)

    def _analyze_results(
        self, results: List[Dict[str, Any]], num_errors: int
    ) -> Dict[str, Any]:
        """Analyze evaluation results and check against PRD criteria."""
        router_results = [r for r in results if r["policy"] == "router"]
        baseline_results = [r for r in results if r["policy"] == "always-medium"]

        router_cost = sum(r["cost_usd"] for r in router_results)
        baseline_cost = sum(r["cost_usd"] for r in baseline_results)

        router_latency = (
            sum(r["latency_ms"] for r in router_results) / len(router_results)
            if router_results
            else 0
        )
        baseline_latency = (
            sum(r["latency_ms"] for r in baseline_results) / len(baseline_results)
            if baseline_results
            else 0
        )

        correct_routes = sum(
            1 for r in router_results if r["expected_model"] == r["model_logical"]
        )
        routing_accuracy = (
            (correct_routes / len(router_results) * 100) if router_results else 0
        )

        savings_usd = baseline_cost - router_cost
        savings_pct = (savings_usd / baseline_cost * 100) if baseline_cost > 0 else 0

        savings_ok = savings_pct > 50
        accuracy_ok = routing_accuracy > 85

        return {
            "timestamp": datetime.now().isoformat(),
            "total_prompts": len(TEST_PROMPTS),
            "total_requests_attempted": len(TEST_PROMPTS) * 2,
            "total_requests_completed": len(results),
            "total_errors": num_errors,
            "router": {
                "total_cost_usd": router_cost,
                "avg_latency_ms": router_latency,
                "routing_accuracy_pct": routing_accuracy,
                "correct_routes": correct_routes,
                "total_fallbacks": sum(1 for r in router_results if r["fallback"]),
            },
            "baseline": {
                "total_cost_usd": baseline_cost,
                "avg_latency_ms": baseline_latency,
            },
            "savings": {
                "usd": savings_usd,
                "percent": savings_pct,
            },
            "detailed_results": results,
        }
    
async def main():
    """Main evaluation function."""
    router_url = os.getenv("ROUTER_URL", "http://localhost:8001")
    api_key = os.getenv("MISTRAL_API_KEY")
    model_small = os.getenv("MODEL_SMALL", "mistral-small-latest")
    model_medium = os.getenv("MODEL_MEDIUM", "mistral-medium-latest")

    if not api_key:
        print("Error: MISTRAL_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    evaluator = RouterEvaluator(router_url, api_key, model_small, model_medium)

    try:
        results = await evaluator.run_evaluation()

        print("\n" + "=" * 60)
        print("EVALUATION RESULTS")
        print("=" * 60)

        print(f"\nTimestamp: {results['timestamp']}")
        print(
            f"Total Prompts: {results['total_prompts']} "
            f"(Completed: {results['total_requests_completed']}/{results['total_requests_attempted']}, "
            f"Errors: {results['total_errors']})"
        )

        print("\n--- Router Performance ---")
        print(f"  Total Cost: ${results['router']['total_cost_usd']:.8f}")
        print(f"  Avg Latency: {results['router']['avg_latency_ms']:.2f}ms")
        print(f"  Total Fallbacks: {results['router']['total_fallbacks']}")
        print(
            f"  Routing Accuracy: {results['router']['routing_accuracy_pct']:.1f}% "
            f"({results['router']['correct_routes']}/{results['total_prompts']})"
        )

        print("\n--- Baseline (Always Medium) ---")
        print(f"  Total Cost: ${results['baseline']['total_cost_usd']:.8f}")
        print(f"  Avg Latency: {results['baseline']['avg_latency_ms']:.2f}ms")

        print("\n--- Savings ---")
        print(
            f"  Cost Reduction: ${results['savings']['usd']:.8f} "
            f"({results['savings']['percent']:.1f}%)"
        )

        output_file = "eval_results.json"
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\nDetailed results saved to: {output_file}")

    except httpx.ConnectError:
        print(
            f"\nError: Could not connect to router at {router_url}", file=sys.stderr
        )
        print(f"Please ensure the router is running.", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(
            f"\nError: HTTP Error {e.response.status_code} from router.",
            file=sys.stderr,
        )
        if e.response.status_code == 401:
            print(
                "Authentication failed. Is MISTRAL_API_KEY correct?", file=sys.stderr
            )
        else:
            print(f"Response: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        await evaluator.close()


if __name__ == "__main__":
    asyncio.run(main())