# ADR-016: A cheap model researches, a stronger model answers

- **Status**: Accepted (Brain Notebook)
- **Date**: 2026-10
- **Related**: [ADR-014](ADR-014-agentic-notebook-chat.md)

## Context

The research loop re-sends a growing transcript at every tool step, so with one model most of a question's cost and
latency was the loop, not the answer. Reasoning models added a second problem: with mandatory or unbounded thinking
they sometimes spent the whole output budget reasoning and returned an empty reply (outlines, captions, answers).

## Decision

**The loop runs on the default *tools* model; the *chat* model (or the session's model) writes the answer once**
from the flattened transcript, with the answer rules in place of the researcher's instructions. The researcher ends
with short findings, not prose, and its text is not streamed. **Every model call has a thinking budget** through
OpenRouter's `reasoning.max_tokens` (`limit_reasoning`): 2,048 per research step, 3,072 for the writer, 1,024 for
utility calls; an empty answer is retried once with less.

## Alternatives considered

- **One model for everything**: simpler, ~3× the cost on the eval, and slower.
- **`reasoning.effort` instead of a token budget**: Qwen3.7 ignores effort levels and GLM-5.3 can't disable
  reasoning; the token budget is the control both honor (measured).
- **Let the research model answer**: cheaper still, but the answer is what the user reads and picks a model for
  (the chat's model selector); keeping it on the chat model keeps that choice meaningful.

## Consequences

- On the 35-question eval: all answers correct, ~$0.003 per question, median ~37 s.
- Two slots must be configured; an unset Tools Model falls back to the chat model (works, costs more).
- The writer sees tool results as text; images the agent viewed are passed along.
