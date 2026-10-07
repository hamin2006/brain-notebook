# Prompt Engineering

How prompts are organized and the patterns they use. All prompts are Jinja2 templates under `prompts/`, rendered with the [ai-prompter](https://github.com/lfnovo/ai-prompter) library — prompt engineering lives in templates, not Python.

## Layout & rendering

Templates are grouped by workflow and referenced by path without extension. The ones Brain Notebook runs:

| Folder | Templates | Used by |
|---|---|---|
| `agent/` | `system` (the research agent; also renders the writer's rules, with a `researcher` flag), `subagent` (delegated per-document agents), `review` (deep-mode sufficiency check, JSON), `compact` (running conversation summary) | `open_notebook/agent/graph.py` |
| `sources/` | `page_caption` (vision caption of a page), `outline` (metadata + topic sections, JSON), `section_summary`, `document_summary`, `concepts` (concept graph, JSON) | `commands/page_commands.py`, `analyze_commands.py`, `concept_commands.py` |
| `podcast/`, transformations | as in Brain Notebook | |
| `ask/`, `chat/`, `source_chat/` | upstream's pre-agent prompts, kept for the legacy graphs | not used by the routers |



```python
from ai_prompter import Prompter
prompt = Prompter(prompt_template="ask/entry", parser=parser).render(data=state)
```

Mechanical rules (path syntax, `data=` key matching, parser injection, no inheritance, cache → restart) are in [`open_notebook/AGENTS.md`](../../open_notebook/AGENTS.md). This page covers the *patterns*.

## Pattern: one system prompt, two roles (agent)

`agent/system.jinja` is rendered twice per turn: with `researcher=True` for the tool-calling research model (how to
use the tools, end with concise findings and addresses) and without it for the answer writer (answer rules,
grounding, citation format). Shared sections (addresses and citations, memories, conversation summary, the web) stay
identical, so both models follow the same citation contract. Grounding (`strict`) and `web_enabled` switch blocks on
and off; tool behavior (dedupe, budgets) is enforced in code, not prompt text.

## Pattern: evidence-first rules

The agent prompt is a short list of working rules rather than a persona: locate with search/outline, then read or
view before relying on something; grep for exhaustive questions; rephrase an empty search once; stop when reads stop
changing the answer; cite the most specific address actually read; never invent one. These rules, plus tool
descriptions written as primitives ("like `ls`", "like `grep`"), did more for answer quality than model choice.

## Pattern: conditional variable injection

Templates accept optional variables via Jinja conditionals, so one template serves several context shapes (podcast outline handles list or string context; source_chat injects optional notebook/insight data):

```jinja
{% if notebook %}
# PROJECT INFORMATION
{{ notebook }}
{% endif %}
```

Watch the loose truthiness (`{% if var %}` is false for empty string/list) and the for-loop assumption (passing a string where a list is expected iterates character by character).

## Pattern: repeated citation emphasis

Response-generating templates (the agent's system prompt, and upstream's ask/chat) state the citation rules — addresses like `[source:abc#p94]`, "use addresses exactly as the tools printed them; never invent one" — **with inline examples**. LLMs hallucinate citations without this; repetition + examples measurably reduces it. Keep the repetition when editing these templates.

## Pattern: format-instructions delegation

Templates expose an `{{ format_instructions }}` slot filled by the caller's OutputParser. Output format evolves in Python (Pydantic models) without touching the template. If the placeholder is missing, the parser is silently ignored — check for it when adding structured output.

## Pattern: JSON from models that write LaTeX

Outline and concept templates ask for JSON, and lecture content invites LaTeX, whose backslashes are invalid JSON
escapes. Ask for plain words where LaTeX isn't needed (the concept template does) and parse leniently
(`open_notebook/utils/concepts.py: parse_extraction` doubles stray backslashes, tolerates fences and prose). Reasoning
models also need a thinking budget (`limit_reasoning`) or they return nothing.

## Pattern: extended-thinking separation (podcast)

Podcast templates instruct thinking models to keep reasoning inside `<think>` tags and emit the JSON after them; `clean_thinking_content()` strips the tags downstream. If a new template expects structured output from thinking-capable models, include the same instruction block.
