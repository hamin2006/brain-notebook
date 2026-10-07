# AI Providers

Brain Notebook talks to AI models through providers. You connect a provider once in **Manage → Models**, pick which of its models to use, and choose a default model for each job (research, answers, document analysis, embeddings, transcription).

This page has four parts:

1. [Models for the research agent](#models-for-the-research-agent): the recommended setup and what each slot does
2. [Connect a provider](#connect-a-provider): adding a configuration by hand
3. [Supported providers](#supported-providers): what each provider can do
4. [Choosing providers](#choosing-providers): which combination fits your setup

Per-provider details (where to get a key, base URLs, regional endpoints) are in the [AI Providers Configuration Guide](../5-CONFIGURATION/ai-providers.md).

---

## Models for the research agent

Brain Notebook uses each default model slot for a specific job. The recommended set is all on **OpenRouter**, one key:

| Slot | Recommended | Used for | Requirements |
|---|---|---|---|
| **Tools Model** | `qwen/qwen3.7-flash` | The research agent: every tool call, sub-agents, the deep-mode reviewer, conversation summaries, concept extraction | **Tool calling**; **vision** so it can `view` pages; cheap and fast, it's called many times per question |
| **Chat Model** | `z-ai/glm-5.3-flash` | Writes the answer (once per question) in chat, source chat, Ask and MCP `ask` | A good writer; vision lets it see pages the agent viewed |
| **Transformation Model** | `z-ai/glm-5.3-flash` | Page captions, document analysis (outline, metadata, summaries), transformations, note titles | **Vision** for captions |
| **Large Context Model** | `z-ai/glm-5.3-flash` | Any prompt over ~105K tokens (rare with the agent) | Long context |
| **Embedding Model** | `qwen/qwen3-embedding-8b` | Passage, section, document, note, memory and concept search | Any embedding model; changing it later needs a rebuild |
| (Settings → Research agent) | `voyageai/rerank-3-lite` | Reranking search candidates | OpenRouter credential |
| (Settings → Research agent) | `google/gemini-embedding-2` | Page-image embeddings for visual search | OpenRouter credential |

On the 35-question course eval this set answers every question at about $0.003 per question.

### Set them up with one command

With the API running, from the repository folder:

```bash
OPENROUTER_API_KEY=sk-or-... python3 scripts/brain/provision_models.py
```

It needs only Python 3. It creates (or reuses) an OpenRouter configuration named `brain-openrouter`, adds the three
models, sets all the defaults above, and tests each model. Re-running it is safe. Options: `--key-file <dotenv>`
(reads `OPENROUTER_API_KEY=` from a file), `--api http://host:5055/api`. Without a key it prompts for one.

### Or by hand

1. [Connect a provider](#connect-a-provider): add an **OpenRouter** configuration with your key and test it.
2. Add **Language** models `z-ai/glm-5.3-flash` and `qwen/qwen3.7-flash`, and **Embedding** model
   `qwen/qwen3-embedding-8b` (type the names in the search box of **Discover Models** if they aren't listed).
3. Under **Default Model Assignments** set Chat, Transformation and Large Context to GLM, **Tools** to Qwen3.7 Flash,
   Embedding to the Qwen embedding model.

### Other providers

Any provider works for chat and embeddings. Pick a fast, inexpensive model with tool calling (and ideally vision) as
the **Tools Model**, your preferred writer as the **Chat Model**, and a vision-capable model as the **Transformation
Model**. Reranking and visual page search call OpenRouter; without an OpenRouter credential, clear both models in
**Settings → Research agent** (search then uses fused vector + keyword ranking, and `search(level="page")` is off).

Reasoning models are fine: Brain Notebook caps their thinking budget per call (2,048 tokens per research step, 3,072
for the answer, 1,024 for utility calls) so they can't spend the whole output limit thinking.

---

## Connect a provider

Do this after Brain Notebook is running and you can open the UI. It ends with a working chat.

> **Before you start:** `OPEN_NOTEBOOK_ENCRYPTION_KEY` must be set (every install guide sets it). If it isn't, the Models page shows "Encryption key not configured" and won't store keys.

### 1. Add a configuration

1. In the left sidebar, under **Manage**, click **Models**.
2. Find your provider in the list and click **Add Configuration**.
3. Fill in the form:
   - **Configuration Name**: any label, for example `Personal`.
   - **API Key**: the key from your provider. Local providers such as Ollama and oMLX don't need one (the field is marked optional).
   - **Base URL**: leave empty for cloud providers. Local and self-hosted providers need it (for example `http://ollama:11434` for the Ollama container).
   - **Google Vertex AI** uses a different form: **GCP Project ID** and **Region** (required) and an optional **Service Account JSON Path** instead of an API key. Without the JSON path, the server's default Google Cloud credentials are used.
4. Click **Add Configuration**.

### 2. Test the connection

On the new configuration, click **Test** (tooltip: *Test Connection*). A green check means Brain Notebook reached the provider with your key. A red cross means the key, the base URL or the network is wrong; see [Troubleshooting](#troubleshooting).

### 3. Add models

1. On the same configuration, click **Models** (tooltip: *Sync Models*). The **Discover Models** dialog lists the models the provider offers.
2. Set **Model Type** first: `Language`, `Embedding`, `TTS` or `STT`. The list isn't filtered by type, so pick the type, then tick only models of that type.
3. Tick the models you want (or type a name in the search box to add one that isn't listed) and click **Add (N)**.
4. Open the dialog again for each other type you need. At minimum add one **Language** model and one **Embedding** model.

### 4. Set default models

Scroll down to **Default Model Assignments** on the same page.

- While a required default is missing, a notice lists it with an **Auto-assign Defaults** button. Click it to fill **Chat Model** and **Embedding Model** from the models you added.
- Or pick each default from its dropdown. Changes save immediately.

| Default | Required | Used for |
|---|---|---|
| **Chat Model** | Yes | Writes the research agent's answers (chat, source chat, Ask, MCP) |
| **Embedding Model** | Yes | All search |
| **Tools Model** | No (uses the chat model) | The research agent's tool calls; set a cheap tool-calling model here |
| **Transformation Model** | No (uses the chat model) | Captions, document analysis, transformations |
| **Large Context Model** | No (uses the chat model) | Any prompt over ~105K tokens |
| **Speech-to-Text Model** | No | Transcribing audio and video sources |
| **Text-to-Speech Model** | No | Not used yet: podcasts use the voice model set in each speaker profile |

**Auto-assign Defaults** only fills Chat Model and Embedding Model; set the **Tools Model** yourself (see [above](#models-for-the-research-agent)). Set Speech-to-Text by hand if you want audio/video transcription; for podcasts, pick a voice model in each speaker profile (**Podcasts → Profiles**).

### 5. Check that chat works

1. In the sidebar, click **Notebooks** → **New Notebook**, enter a name and click **Create New Notebook**.
2. In the notebook, click the **Add Source** button and pick **Add Source** from its menu (the other entry, **Add Existing Sources**, reuses sources you already have). Choose **Enter Text**, paste a paragraph, give it a title, then click **Next** through the remaining steps and **Done**.
3. Wait for the source to finish processing, then type a question in the chat panel and send it with **Ctrl+Enter** (**⌘+Enter** on macOS).

If you get an answer, you're done. Add more providers the same way at any time; each one gets its own configurations and models.

### Troubleshooting

- **Test fails on a cloud provider**: check the key on the provider's website and that the account has credit. Edit the configuration to replace the key.
- **Test fails on a local provider**: the base URL must be reachable *from the Brain Notebook container*, not from your browser. `localhost` inside the container is the container itself. See [Ollama](../5-CONFIGURATION/ollama.md).
- **Chat says "No model configured…"**: a default is empty. Go back to step 4.
- **Source stays queued forever**: the background worker isn't running. In Docker it runs inside the `open_notebook` container (check `docker compose logs open_notebook`); from source you start it yourself.
- **"Decryption Error" on a configuration**: `OPEN_NOTEBOOK_ENCRYPTION_KEY` changed since the key was saved. Delete the configuration and add it again.
- More: [AI & Chat Issues](../6-TROUBLESHOOTING/ai-chat-issues.md).

---

## Supported providers

Brain Notebook supports 24 providers. The table lists the model types each provider offers when you add a configuration. What you can actually add depends on the models in your provider account.

| Provider | Language | Embedding | Speech-to-Text | Text-to-Speech | Setup |
|---|:-:|:-:|:-:|:-:|---|
| OpenAI | ✅ | ✅ | ✅ | ✅ | [guide](../5-CONFIGURATION/ai-providers.md#openai) |
| Anthropic | ✅ | | | | [guide](../5-CONFIGURATION/ai-providers.md#anthropic-claude) |
| Google AI (Gemini) | ✅ | ✅ | ✅ | ✅ | [guide](../5-CONFIGURATION/ai-providers.md#google-gemini) |
| Groq | ✅ | | ✅ | | [guide](../5-CONFIGURATION/ai-providers.md#groq) |
| Mistral AI | ✅ | ✅ | ✅ | ✅ | |
| DeepSeek | ✅ | | | | |
| xAI (Grok) | ✅ | | | ✅ | |
| OpenRouter | ✅ | ✅ | ✅ | ✅ | [guide](../5-CONFIGURATION/ai-providers.md#openrouter) |
| DashScope (Qwen) | ✅ | | | | [guide](../5-CONFIGURATION/ai-providers.md#dashscope-qwen) |
| MiniMax | ✅ | | | ✅ | [guide](../5-CONFIGURATION/ai-providers.md#minimax) |
| Novita | ✅ | | | | [guide](../5-CONFIGURATION/ai-providers.md#novita) |
| SiliconFlow | ✅ | | | | [guide](../5-CONFIGURATION/ai-providers.md#siliconflow) |
| Z.ai | ✅ | | | | [guide](../5-CONFIGURATION/ai-providers.md#zai) |
| PayPerQ (PPQ) | ✅ | ✅ | ✅ | ✅ | [guide](../5-CONFIGURATION/ai-providers.md#payperq-ppq) |
| Cohere | ✅ | ✅ | | | [guide](../5-CONFIGURATION/ai-providers.md#cohere) |
| Voyage AI | | ✅ | | | |
| ElevenLabs | | | ✅ | ✅ | |
| Deepgram | | | ✅ | ✅ | |
| Ollama (local) | ✅ | ✅ | | | [guide](../5-CONFIGURATION/ollama.md) |
| oMLX (local, Apple Silicon) | ✅ | ✅ | | | [guide](../5-CONFIGURATION/omlx.md) |
| Azure OpenAI | ✅ | ✅ | ✅ | ✅ | [guide](../5-CONFIGURATION/ai-providers.md#azure-openai) |
| Google Vertex AI | ✅ | ✅ | | ✅ | |
| OpenAI Compatible | ✅ | ✅ | ✅ | ✅ | [guide](../5-CONFIGURATION/openai-compatible.md) |
| Anthropic Compatible | ✅ | | | | [guide](../5-CONFIGURATION/ai-providers.md#anthropic-compatible) |

**OpenAI Compatible** covers any server that speaks the OpenAI API: LM Studio, vLLM, LocalAI, and self-hosted speech servers ([local TTS](../5-CONFIGURATION/local-tts.md), [local STT](../5-CONFIGURATION/local-stt.md)). LM Studio has no provider of its own; add it as OpenAI Compatible.

---

## Choosing providers

Brain Notebook needs at least a **language** model and an **embedding** model; the research agent works best with a cheap tool-calling model for research plus a stronger one for answers, and a vision model for captions. **OpenRouter is the recommended single provider**: it covers all of these plus reranking and page-image embeddings. Podcasts also need **text-to-speech**.

**One provider for everything.** OpenAI, Google AI, Mistral AI, OpenRouter, PayPerQ and Azure OpenAI offer all four model types under one key. This is the simplest setup.

**Language-only providers need a partner.** Anthropic, DeepSeek, DashScope, Novita, SiliconFlow, Z.ai and Anthropic Compatible offer only language models. Add a second provider for embeddings (and for text-to-speech if you want podcasts), for example OpenAI, Google AI, Mistral AI, Voyage AI or a local Ollama.

**Fully local.** Ollama and oMLX provide language and embedding models on your own hardware. For podcasts and transcription without the cloud, add a local speech server through OpenAI Compatible ([local TTS](../5-CONFIGURATION/local-tts.md), [local STT](../5-CONFIGURATION/local-stt.md)). Local models are slower on CPU; a GPU or Apple Silicon helps.

**Mixing is normal.** Each default model can come from a different provider, for example a cloud chat model with local embeddings.

**Changing the embedding model later** means rebuilding existing embeddings. The UI asks before switching and links to the rebuild on the **Advanced** page.

Prices, context windows and model line-ups change often, so this guide doesn't list them. Check each provider's own pricing and model pages.

---

## Next steps

- [AI Providers Configuration Guide](../5-CONFIGURATION/ai-providers.md): per-provider keys, base URLs and regional endpoints
- [Ollama](../5-CONFIGURATION/ollama.md): local models, networking and timeouts
- [User Guide](../3-USER-GUIDE/index.md): adding sources, chat, podcasts

