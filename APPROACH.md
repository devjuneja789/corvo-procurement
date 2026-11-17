# Approach and AI usage

Built with OpenAI Codex assistance for planning, implementation, local PDF extraction, synthetic tests, debugging and documentation. The candidate must review and understand the implementation before submission and be able to explain or modify it.

Python 3.12 provides the backend HTTP API and SQLite persistence; the frontend uses HTML, CSS and vanilla JavaScript. The core runs without installed packages. Docker installs pypdf for broader PDF compatibility; a bounded fallback reads the kit's embedded text and font maps. The source tree contains synthetic fixtures rather than the supplied kit.

The procurement engine is a pure deterministic function. It uses Decimal arithmetic, sorted anchored grouping, ordered policy predicates, contract-consumption ledgers scoped to each run, explainable supplier scores, and PO consolidation. SQLite stores immutable policy versions and sources, upload fingerprints, complete run snapshots, approvals, purchasing documents, contract reservations, chat state and audit events.

An optional OpenRouter Chat Completions integration interprets chat fields and policy/amendment documents. Configure OPENROUTER_API_KEY and optionally OPENROUTER_MODEL on the server. The default model is openai/gpt-4.1-mini; change the environment variable if a different available model is preferred. AI never computes procurement outcomes or directly activates policies. Structured outputs are validated, source changes are shown, and a buyer must approve policy drafts. Without a key, catalog-based chat and complete JSON policy editing/upload remain available. Inputs supplied to that optional service include the relevant catalog and request text, or the base policy and amendment text.

The interface focuses on conversational employee intake and a buyer's next action: import, process, inspect evidence, approve, or record an override. The Render blueprint uses Docker, a persistent SQLite disk, and disabled automatic deployment for the build freeze.

Validation: synthetic engine boundary tests and in-process tests of the actual API dispatcher, plus private sample-batch verification. See README for commands and the verification limitations. No task-specific PR answers are encoded in the engine. The implementation plan and original kit remain ignored by Git.
