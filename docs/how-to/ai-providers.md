# AI providers, models and spend

Blindspot talks to four kinds of provider. Administrators add them; everyone signed in can see
them (never their keys). Viewers cannot change anything.

| Kind           | Default address                     | Key      | Private addresses |
| -------------- | ----------------------------------- | -------- | ----------------- |
| `anthropic`    | `https://api.anthropic.com`         | required | refused           |
| `openai`       | `https://api.openai.com/v1`         | required | refused           |
| `ollama-local` | `http://host.docker.internal:11434` | optional | allowed           |
| `ollama-cloud` | `https://ollama.com`                | required | refused           |

Inside the container, `host.docker.internal` reaches Ollama running on the machine that hosts
Docker. Plain `http` is only allowed for `ollama-local`.

## Keys

A key is sealed with the `providers` purpose (see [Secrets](secrets.md)) the moment it is
saved. The API returns only whether a key exists and its last four characters; the audit trail
records that the key changed, never the key. Rotating the app secret key re-seals provider keys
with everything else.

## The address guard

A provider address is checked when it is saved: `http` or `https`, a host name, no user name,
query or fragment. The name is resolved and **every** address it resolves to is checked. Hosted
kinds must resolve to public addresses only. Link-local, cloud-metadata, unspecified, multicast
and reserved addresses are refused for every kind, so a provider can never be pointed at the
host's metadata service. IPv4-mapped IPv6 addresses are judged as IPv4.

## Models and prices

`GET /api/ai/catalog` lists the built-in models (Anthropic Claude, OpenAI GPT-6 and GPT-5.4
mini and nano) with their prices, in USD per million tokens, the date they were verified and
where (see [Models and pricing](../research/models-and-pricing.md)). Adding a model whose id is
in the catalog fills in its name, context size and capabilities.

A model's price is the first that applies:

1. **override**: a price an administrator set on the model, field by field;
2. **catalog**: the built-in price, including the long-prompt tier (for example Claude Haiku
   above 100,000 prompt tokens, GPT-6 above 272,000);
3. **free**: any model on a local Ollama;
4. **unknown**: the call is recorded without a cost, and its tokens still count.

## The usage ledger and budgets

Every call is added to the usage ledger with its provider, model, agent, run, token classes
(uncached input, output including thinking, cache reads, cache writes at both lifetimes),
latency and cost. A provider can have a **monthly budget** (UTC calendar month). With **hard
stop** on, a call made once the budget is spent is refused with `402 budget_exceeded`;
without it the budget is only shown. Deleting a provider keeps its ledger rows under the name
it had.

## Default model per role

Five roles (commander, category agent, test agent, reporter, chat) can each have a default
model: `GET /api/ai/role-defaults`, `PUT /api/ai/role-defaults/{role}` with a `model_ref`, and
`DELETE` to clear. Only enabled models can be chosen, and removing a model clears the defaults
that used it.

## Trying a provider and fetching models

Both calls are admin-only (they make the server contact the provider with the stored key) and
are recorded in the audit trail without the key.

- `POST /api/providers/{id}/test` asks the provider for its models and returns `200` with
  `{ok, latency_ms, model_count, failure, detail}`. A failure is a result, not an HTTP error, so
  the page can show it beside the button. `failure` is one of `key_rejected`, `unreachable`,
  `rate_limited`, `not_found` (the address is not that provider's API), `provider_error`,
  `bad_response` or `base_url_rejected`. `detail` never quotes the provider's reply or the key.
- `POST /api/providers/{id}/models/fetch` returns the models the account can use, each with
  `added`, the price source and whatever the catalog adds (name, context size, capabilities).
  It adds nothing; the page offers the list and adds the ones picked with the ordinary add-model
  call. A failure is `502` with `provider_<failure>`.

What each kind lists:

| Kind           | How                                                   | Notes                                                             |
| -------------- | ----------------------------------------------------- | ----------------------------------------------------------------- |
| `anthropic`    | Models API through the official SDK, following pages  | Reports thinking and image support per model                      |
| `openai`       | Models API through the official SDK                   | Audio, image and embedding models are left out                    |
| `ollama-local` | `GET /api/tags`, then `POST /api/show` for each model | Capabilities and context size; embedding-only models are left out |
| `ollama-cloud` | The same, with the key as a bearer token              | Cloud does not enforce JSON-schema output                         |

The address is checked again on every call, because a host name can start resolving to a
private address after it was saved. The HTTP client never follows redirects and has a 30 second
timeout (10 to connect). The SDKs retry rate limits and server errors twice.

## The AI providers page

`/ai-providers` (System menu) is where administrators set this up; viewers see the same page
without the buttons that change things.

1. **Add provider.** Pick the kind, give it a name, check the address, paste the key and
   optionally set a monthly budget with whether to stop at the limit. A kind that needs
   no key (local Ollama) can be saved without one.
2. **Test.** The card's Test button asks the provider to list its models. The result says
   _Connected_ and how many models are on offer, or names the failure: the key was rejected, the
   address cannot be reached, the provider is rate limiting, and so on. It never shows the
   response.
3. **Models.** Open a card's models, press _Fetch models_ and tick the ones to add. Prices come
   from the built-in catalog; edit a model to override any of them. Local models are free. A model
   the catalog does not know is saved with unknown prices and shown as such. The switch on each
   row turns a model on or off, and a disabled model cannot be a default.
4. **Defaults for roles.** Choose the model each role uses: the Commander, the category agents,
   the test agents, the reporter and the chat. Changing a default saves immediately.

The budget bar on a card is this month's spend against its budget, from the usage ledger.

### Ollama on the same machine

Blindspot runs inside a container, so `localhost` there is the container itself. To reach Ollama on
the Docker host:

- Keep the default address `http://host.docker.internal:11434`.
- Make Ollama listen beyond loopback: set `OLLAMA_HOST=0.0.0.0` for the Ollama service.
- On Linux, start the container with `--add-host=host.docker.internal:host-gateway`. Docker
  Desktop does this for you.

## Running prompts

`app/ai/engine.py` turns a stored provider into a Pydantic AI model: Anthropic's Messages API,
OpenAI's Responses API, and Ollama's OpenAI-compatible chat endpoint. `cache_settings` switches
prompt caching on: Anthropic caches the instructions, the tool definitions and the conversation
so far; OpenAI groups a run's calls under one `prompt_cache_key`. `usage_of` turns a run's usage
into the same terms the price catalog uses (uncached input, output, cache reads, short and long
cache writes), taking cached tokens out of the input figure for providers that count them in it.
Ollama reports no cached tokens through this path, so its cache reads show as zero. OpenAI's
12-hour cache writes are not reported by Pydantic AI, and Blindspot only asks for the default
30-minute lifetime, so they never arise.

## Errors

| Code                | Status | Meaning                                                       |
| ------------------- | ------ | ------------------------------------------------------------- |
| `key_required`      | 422    | This kind needs a key, or the key was removed                 |
| `base_url_rejected` | 422    | The address failed the guard; the title says why              |
| `name_taken`        | 409    | Another provider has that name                                |
| `model_exists`      | 409    | The provider already has that model                           |
| `model_disabled`    | 409    | A disabled model cannot be a role default                     |
| `budget_exceeded`   | 402    | The monthly budget is used up and the provider is set to stop |
