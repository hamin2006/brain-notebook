# Development

Documentation for people (and coding agents) working on the Brain Notebook codebase. Start with the
[agentic RAG plan](plans/agentic-rag.md): it explains what the fork changed from Open Notebook and why, and records
findings and eval results.

## Start here

1. **[Development Setup](development-setup.md)**: install, configure and run the stack from source.
2. **[Contributing](contributing.md)**: workflow, commit and CHANGELOG conventions, the checks to run, merging upstream.
3. **[Change Playbooks](change-playbooks.md)**: step-by-step recipes for common changes (agent tool, field, endpoint, provider, migration, command, language).

The normative rules for coding agents (and humans in a hurry) are in the `AGENTS.md` files: [root](../../AGENTS.md), [backend](../../open_notebook/AGENTS.md) (also covers `api/`, `commands/`, `prompts/`) and [frontend](../../frontend/AGENTS.md).

## Reference

| Page | What it covers |
|---|---|
| [Agentic RAG plan](plans/agentic-rag.md) | Design of the research agent and ingestion: tasks, tool design, findings, eval results, decisions |
| [Architecture](architecture.md) | Processes, code layout, the agent, ingestion jobs, data model, request paths |
| [Credentials](credentials.md) | Provider credentials, encryption, provider registry, provisioning |
| [Content Processing](content-processing.md) | Page-aware PDF ingestion, chunking, embedding, context building, encryption utility |
| [Podcasts](podcasts.md) | Episode and speaker profiles, model resolution, job lifecycle |
| [Prompts](prompts.md) | Prompt templates and `Prompter` |
| [Frontend](frontend.md) | Next.js layers and data flows |
| [API Reference](api-reference.md) | `/api` prefix, auth, async jobs, streaming, errors; the live schema is at `/docs` |
| [Code Standards](code-standards.md) | Tooling, async, database access, error handling |
| [Testing](testing.md) | Unit and agent tests, real-database integration tests, the agent eval |
| [Security](security.md) | Query, template and file-handling safety; secrets; review checklist |
| [Design Principles](design-principles.md) | Engineering practices and anti-patterns |
| [Decision Records](decisions/README.md) | ADRs and PDRs: why things are the way they are |
| [VISION.md](../../VISION.md) | Product identity, current posture and priorities |
| [Maintainer Guide](maintainer-guide.md) | Upstream Open Notebook's triage process (reference) |

## Getting help

Issues at https://github.com/hamin2006/brain-notebook/issues.

## Libraries from upstream Open Notebook's author

- [Esperanto](https://github.com/lfnovo/esperanto): one interface over the AI providers
- [Content Core](https://github.com/lfnovo/content-core): content extraction
- [Podcast Creator](https://github.com/lfnovo/podcast-creator): podcast generation
- [surreal-commands](https://github.com/lfnovo/surreal-commands): the background job queue
