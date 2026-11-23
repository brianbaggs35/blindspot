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

## Errors

| Code                | Status | Meaning                                                       |
| ------------------- | ------ | ------------------------------------------------------------- |
| `key_required`      | 422    | This kind needs a key, or the key was removed                 |
| `base_url_rejected` | 422    | The address failed the guard; the title says why              |
| `name_taken`        | 409    | Another provider has that name                                |
| `model_exists`      | 409    | The provider already has that model                           |
| `model_disabled`    | 409    | A disabled model cannot be a role default                     |
| `budget_exceeded`   | 402    | The monthly budget is used up and the provider is set to stop |
