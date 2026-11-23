"""The playbook a test gets when nobody has written one for it.

A default is built from its category's template, the test's own name and objectives, and the tools
that can do it. The highest-value tests have hand-written playbooks that replace these (see
`bundled/wstg/playbooks.yaml`), and an administrator can override any of them.
"""

from dataclasses import dataclass

from app.methodology.spec import RISK_ORDER, Playbook, RiskClass, ToolId


@dataclass(frozen=True)
class Template:
    """What is true of every test in a category."""

    focus: str
    safe: tuple[str, ...]
    active: tuple[str, ...]
    intrusive: tuple[str, ...]
    evidence: tuple[str, ...]
    failure: str
    not_applicable: tuple[str, ...]


_EVIDENCE = (
    "The exact request and response that show the behaviour, with timestamps",
    "A short note on why the behaviour is or is not a weakness",
)

TEMPLATES: dict[str, Template] = {
    "WSTG-INFO": Template(
        focus="what the target gives away about itself and how it is put together",
        safe=(
            "Read public sources and the target's own pages, headers and metafiles",
            "Record every entry point, version string and technology you can name",
        ),
        active=(
            "Request well-known paths and error pages once each to see how the server answers",
        ),
        intrusive=(),
        evidence=("The source or response each fact came from", "A list of what was learned"),
        failure=(
            "Sensitive design, version or configuration detail is exposed that an attacker could "
            "use."
        ),
        not_applicable=("The scope excludes the surface this test looks at",),
    ),
    "WSTG-CONF": Template(
        focus="how the platform, server and deployment are configured",
        safe=(
            "Read response headers, TLS settings and published policies",
            "Compare what the target serves with the hardening guidance for its platform",
        ),
        active=("Request default, backup, admin and debug paths and compare the answers",),
        intrusive=(
            "Send methods or paths that could change or remove a resource only against a test "
            "resource the scope names",
        ),
        evidence=_EVIDENCE,
        failure="A setting is missing, weak or default in a way that exposes the application.",
        not_applicable=("The component does not exist in this deployment",),
    ),
    "WSTG-IDNT": Template(
        focus="how identities and roles are defined, created and verified",
        safe=("Read the role documentation and observe what each role is shown",),
        active=("Use the registration, provisioning and verification flows with accounts you own",),
        intrusive=(
            "Create many accounts only when the scope allows it and clean them up afterwards",
        ),
        evidence=("The role or flow tested, the accounts used and what each could do", *_EVIDENCE),
        failure=(
            "An identity can be created, claimed or enumerated in a way the design does not intend."
        ),
        not_applicable=("The application has no sign-in or no self-service accounts",),
    ),
    "WSTG-ATHN": Template(
        focus="whether the application proves who a person is, and keeps that proof safe",
        safe=("Read the sign-in, reset and recovery pages and note every method offered",),
        active=(
            "Try the sign-in and recovery flows with accounts you own and observe every difference",
        ),
        intrusive=(
            "Guess credentials or answers only inside the lock-out limits the scope allows",
            "Ask before any step that could lock a real account",
        ),
        evidence=("Which account was used, the flow, and the response at each step", *_EVIDENCE),
        failure="Authentication can be bypassed, guessed, replayed or weakened.",
        not_applicable=("The application has no authentication",),
    ),
    "WSTG-ATHZ": Template(
        focus="whether each person can only do and see what their role allows",
        safe=(
            "Map which roles, objects and functions exist, from the interface and from the traffic",
        ),
        active=("Repeat each request as another role, another user and no user, and compare",),
        intrusive=("Change or remove another user's data only against test data the scope names",),
        evidence=("The request, the role used and the data or action that was reached", *_EVIDENCE),
        failure="A request succeeds for someone who should be refused.",
        not_applicable=("There is only one role and no per-user data",),
    ),
    "WSTG-SESS": Template(
        focus="how a session is created, carried, kept and ended",
        safe=("Inspect the cookies, tokens and storage the application sets and their attributes",),
        active=("Replay, swap and expire sessions you own and observe how the server reacts",),
        intrusive=("Test concurrent use and token guessing only at a rate the target can bear",),
        evidence=("The token or cookie, its attributes and the behaviour observed", *_EVIDENCE),
        failure="A session can be fixed, stolen, predicted, kept alive too long or reused.",
        not_applicable=("The application keeps no session state",),
    ),
    "WSTG-INJT": Template(
        focus="whether input the application takes is ever treated as instructions",
        safe=(
            "List every input: parameters, headers, bodies, files and anything stored and shown "
            "later",
        ),
        active=("Send harmless probes that reveal how input is interpreted, one input at a time",),
        intrusive=(
            "Escalate to a proof of exploitation only with approval, and stop at the smallest "
            "proof",
            "Use out-of-band probes only when the scope allows traffic to leave the target",
        ),
        evidence=(
            "The input, the probe and the response that shows it was interpreted",
            *_EVIDENCE,
        ),
        failure="Input changes how the application or a system behind it behaves.",
        not_applicable=("The input is never used in this way by the technology in use",),
    ),
    "WSTG-ERRH": Template(
        focus="what the application reveals when something goes wrong",
        safe=("Read the error pages and messages the application already shows",),
        active=("Cause errors with malformed input, odd methods and missing resources",),
        intrusive=(),
        evidence=("The input that caused each error and the full response", *_EVIDENCE),
        failure="An error discloses internals, a stack trace or data.",
        not_applicable=(),
    ),
    "WSTG-CRYP": Template(
        focus="whether data in transit and at rest is protected with sound cryptography",
        safe=("Read the TLS configuration, certificates and the places sensitive data is sent",),
        active=("Probe protocol versions, ciphers and error behaviour",),
        intrusive=(),
        evidence=("The configuration or response that shows the weakness", *_EVIDENCE),
        failure="Data is sent or stored with weak or missing protection.",
        not_applicable=("The service does not use the mechanism being tested",),
    ),
    "WSTG-BUSL": Template(
        focus="whether the rules of the application's own business can be bent",
        safe=("Learn the intended workflow and its limits from the interface and documentation",),
        active=("Repeat, reorder, delay and alter steps with accounts and data you own",),
        intrusive=(
            "Test limits, payments and inventory only with the test items the scope names",
            "Ask before any step with real money or real stock",
        ),
        evidence=("The workflow, the step altered and the outcome that broke the rule", *_EVIDENCE),
        failure="A rule can be bypassed, repeated or abused to the application owner's harm.",
        not_applicable=("The application has no such function",),
    ),
    "WSTG-CLNT": Template(
        focus="what runs in the person's browser and what it trusts",
        safe=("Read the page source, scripts, storage and the headers that govern the browser",),
        active=(
            "Drive the page in an instrumented browser and observe what runs and what it sends",
        ),
        intrusive=(),
        evidence=("The page, the script or message involved and what the browser did", *_EVIDENCE),
        failure="Attacker-controlled data reaches a place where the browser acts on it.",
        not_applicable=("The feature is not used by the application",),
    ),
    "WSTG-APIT": Template(
        focus="how the application's API is described, protected and limited",
        safe=("Collect the API description and every endpoint the client calls",),
        active=("Call each endpoint as each role and with altered objects, fields and methods",),
        intrusive=("Test rate limits and resource use only at a rate the target can bear",),
        evidence=(
            "The endpoint, the role and the request and response that show the behaviour",
            *_EVIDENCE,
        ),
        failure="An endpoint exposes, accepts or allows more than its design intends.",
        not_applicable=("The application has no such API",),
    ),
    "WSTG-WASM": Template(
        focus="the WebAssembly the application ships and what it exposes",
        safe=("Download and list every module, its imports and exports",),
        active=("Run the module in a sandbox and observe what it does with controlled input",),
        intrusive=(),
        evidence=("The module hash and the finding location inside it", *_EVIDENCE),
        failure="The module exposes secrets, logic or behaviour an attacker can use.",
        not_applicable=("The application uses no WebAssembly",),
    ),
}

GENERIC = Template(
    focus="the objectives listed for this test",
    safe=("Observe and record how the target behaves before sending anything unusual",),
    active=("Send the smallest request that shows whether the behaviour is present",),
    intrusive=("Ask before any step that could change data or disturb the service",),
    evidence=_EVIDENCE,
    failure="The behaviour the objectives describe is present.",
    not_applicable=("The scope excludes it, or the target does not have the feature",),
)


def template_for(category_id: str) -> Template:
    """The template for a category, or the generic one."""
    return TEMPLATES.get(category_id, GENERIC)


def generated_playbook(
    *,
    category_id: str,
    test_name: str,
    objectives: list[str],
    tools: list[ToolId],
    manual_review: bool,
    risk_class: RiskClass,
    approach: str | None,
) -> Playbook:
    """The playbook for a test that has none of its own. Steps above the test's risk class are
    left out, so a safe test never lists an intrusive step."""
    template = template_for(category_id)
    allowed = RISK_ORDER[: RISK_ORDER.index(risk_class) + 1]
    goals = "\n".join(f"- {goal}" for goal in objectives) or "- Establish whether it is present."
    how = f"\n\nSuggested approach: {approach.rstrip('.')}." if approach else ""
    instructions = (
        f"Test: {test_name}.\n\nYou are checking {template.focus}.\n\nObjectives:\n{goals}{how}\n\n"
        "Work from the least intrusive step to the most. Stay inside the scope. Record the exact "
        "request and response for everything you rely on, and say plainly when you could not tell."
    )
    if manual_review:
        instructions += (
            " This test is judgement work: gather the evidence, give your reasoning and mark the "
            "result for a person to review."
        )
    return Playbook(
        summary=f"Check {test_name.lower()}: {template.focus}.",
        instructions=instructions,
        tools=tools,
        manual_review=manual_review,
        safe_steps=list(template.safe),
        active_steps=list(template.active) if RiskClass.ACTIVE in allowed else [],
        intrusive_steps=list(template.intrusive) if RiskClass.INTRUSIVE in allowed else [],
        evidence=list(template.evidence),
        success=f"Every objective was checked and no weakness was found in {test_name.lower()}.",
        failure=template.failure,
        not_applicable=list(template.not_applicable),
    )
