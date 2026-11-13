# Model fallback and the documents intent (owner, 2026-11-12)

## Why
The AI search planner answered "What we can't do: reading uploaded documents and summarizing court cases" to
"tell me something about the court case I just uploaded". That text came from FURP's own planner, not from a
model refusing: the system prompt in `app/ask.py` told the model to call the `unknown` tool for anything outside
the listed searches, and that tool's description asked for "what can't be done" and "the closest supported
question", which `templates/search_nl.html` printed. Uploaded documents simply were not in the menu.

## What changed
- `app/ask.py`: a `documents` tool (uploaded documents, mailboxes, court cases, "the file I just uploaded") and a
  sentence about uploads in the system prompt. `app/main.py` runs that intent through `app/documents_search.py`
  outside the shared result cache (what one reader may see another may not); it calls
  `app.space_ingest.search_documents(conn, user, text, limit)` (the ingestion pipeline) with the reader's marks and
  writes the short answer on top from the rows with `app/answer.py`. Until the pipeline exists the page says the
  documents are not extracted yet, never "can't do".
- `app/llm_fallback.py`: every step that plans or summarizes (planner, deep-query plan and answer, short answer,
  page explanations) detects a refusal (phrases such as "I can't", "I'm unable", "cannot assist", a refusal stop,
  prose instead of a tool call) or a failure, or an "unknown"/"unsupported" plan for a request the site supports
  (words for uploads, documents, court cases and the known tables), and retries the same request through
  OpenRouter with `LLM_FALLBACK_MODELS` in order (comma-separated OpenRouter ids in `.env`; default
  `anthropic/claude-opus-5.5,openai/gpt-5.6-terra,google/gemini-4-carbon,x-ai/grok-4.7`). Anthropic-only request
  fields are dropped for other providers. Needs `OPENROUTER_API_KEY` in `.env` (present on both boxes).
- The user sees one line when it happened: "The first model (X) declined this request, so we retried with Y."
  (on the search page, at the top of a deep query, as the first sentence of a retried short answer).
- Every attempt (step, model, outcome, ms, detail) goes to the log and to the table `llm_attempts` (created on
  first use), listed at the bottom of `/admin` (last 50).
- When every model fails, the page shows the last real error ("The search planner could not run this request:
  …"), never a rewritten "closest search" suggestion.

## Tests
`tests/test_llm_fallback.py` (no real model calls).
