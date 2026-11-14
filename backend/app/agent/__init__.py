"""SPankkiBot AI agent: a tool-calling financial coach over the customer's own data.

Why this package exists
-----------------------
The S-Pankki "Personal Economic Trainer" challenge asks for a coach that people can
*talk to about their own money*. A plain chatbot cannot do that safely: it would
guess numbers. This package therefore wraps an open-weights LLM (Nemotron, served
through an OpenAI-compatible API) in a strict tool loop:

    user question ──► orchestrator ──► LLM decides which analytics tool to call
                         ▲   │                     │
                         │   └── SSE events ◄──────┤ (status / tool / widget / token)
                         │                         ▼
                         └──────── compact aggregates from app.analytics (DuckDB)

* ``settings``     – one place that reads env / .env (provider chain, AS_OF, flags).
* ``llm``          – resilient provider chain (timeouts, one retry, 60 s circuit breaker,
                     streamed tool-call accumulation, reasoning never leaked).
* ``personas``     – Sisu the Trainer and Aava the Mentor (human coach characters): same tools, different pedagogy.
* ``tools``        – JSON schemas + executors; every tool returns a ``ToolResult`` with an
                     LLM payload (aggregates only — privacy by design), typed generative-UI
                     widgets for the app, and provenance (``tx_count``, ``period``).
* ``orchestrator`` – the async generator behind ``POST /api/chat`` (SSE protocol, SPEC §4.2).
* ``fallback``     – an offline, rule-based intent router so the demo works with no LLM.
* ``evals``        – scripted challenge questions + a grounding checker (no invented numbers).
"""
