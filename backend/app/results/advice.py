"""What to tell a person about each kind of finding: what it means, why it matters and what to do.

Advice is looked up by the finding's `reference`: an exact match first, then the longest prefix.
Text is written once here, so every tool says the same thing in the same words and nothing a tool
printed (a header value, a token, a page's own text) is ever copied into it.
"""

from dataclasses import dataclass

from app.tools.parsers.schema import Severity


@dataclass(frozen=True)
class Advice:
    what: str
    why: str
    todo: str


ADVICE: dict[str, Advice] = {
    "headers:no-hsts": Advice(
        "The site does not tell browsers to always use https.",
        "A visitor on a hostile network can be pushed to the plain http version and watched.",
        "Send a Strict-Transport-Security header with a long max-age on every https answer.",
    ),
    "headers:short-hsts": Advice(
        "The HSTS rule expires quickly.",
        "Protection lapses soon after a visitor leaves, so the downgrade risk comes back.",
        (
            "Raise max-age to at least six months, and add includeSubDomains once every subdomain "
            "uses https."
        ),
    ),
    "headers:no-nosniff": Advice(
        "The page does not stop browsers guessing what kind of file it is.",
        "A browser may run an uploaded file as script if it looks like script.",
        "Send X-Content-Type-Options: nosniff.",
    ),
    "headers:framing": Advice(
        "Other sites can put this page inside a frame.",
        (
            "An attacker can overlay it with a decoy so visitors click things they cannot see "
            "(clickjacking)."
        ),
        "Send a CSP frame-ancestors directive (or X-Frame-Options: DENY) unless framing is wanted.",
    ),
    "headers:referrer": Advice(
        "The page may send its full address to other sites.",
        "Addresses sometimes hold tokens, ids or search terms that should stay private.",
        "Send Referrer-Policy: strict-origin-when-cross-origin or stricter.",
    ),
    "headers:no-permissions-policy": Advice(
        "Powerful browser features are not switched off for this page.",
        "Injected or embedded content could ask for the camera, microphone or location.",
        "Send a Permissions-Policy header that turns off the features the site does not use.",
    ),
    "headers:no-csp": Advice(
        "The site has no Content-Security-Policy.",
        "If script is ever injected into a page, nothing stops it running or sending data out.",
        "Add a CSP that limits script to the site's own files, then tighten it step by step.",
    ),
    "headers:leak-": Advice(
        "A header announces the exact software and version.",
        "It saves an attacker the work of finding out which known flaws apply.",
        "Remove the version from the header, and keep the software up to date anyway.",
    ),
    "headers:cookie": Advice(
        "A cookie is missing protective settings.",
        (
            "Without them script can read it, it can travel over unencrypted connections or other "
            "sites can trigger requests with it."
        ),
        "Set Secure, HttpOnly and SameSite on every cookie that holds a session.",
    ),
    "headers:cors-reflected": Advice(
        "The site lets any website read its answers by repeating back whatever origin asks.",
        "A malicious page can read private data from a visitor who is signed in.",
        "Allow only a fixed list of trusted origins, and never repeat the Origin header back.",
    ),
    "headers:cors-": Advice(
        "The site's cross-origin sharing rules are too open.",
        "Other websites may be able to read answers meant only for the site's own pages.",
        "Share only with the origins that need it, and never together with credentials.",
    ),
    "csp:": Advice(
        "The Content-Security-Policy has a weak spot.",
        "A weak policy gives a false sense of safety: injected script can still run.",
        (
            "Remove unsafe-inline and unsafe-eval, use nonces or hashes, and list only hosts you "
            "control."
        ),
    ),
    "jwt:alg-none": Advice(
        "The login token claims it needs no signature.",
        "If the server believes that, anyone can write a token for any user.",
        "Reject tokens with alg none, and fix the allowed algorithms on the server.",
    ),
    "jwt:no-signature": Advice(
        "The login token has no signature.",
        "A server that accepts it lets anyone change who they say they are.",
        "Always verify the signature, and refuse tokens without one.",
    ),
    "jwt:hmac": Advice(
        "The token is signed with a shared secret.",
        "A short or guessable secret can be found offline, after which tokens can be forged.",
        (
            "Use a long random secret (or a public-key algorithm) and never accept a different "
            "algorithm than expected."
        ),
    ),
    "jwt:": Advice(
        "The login token has a weakness.",
        "Tokens are what keeps people signed in, so a weak one can be abused or forged.",
        (
            "Check the signing, expiry and header of tokens on the server as the technical view "
            "describes."
        ),
    ),
    "wellknown:robots": Advice(
        "robots.txt lists paths the site does not want search engines to visit.",
        "It is public, so it reads like a map of the places someone thought were worth hiding.",
        "Do not rely on it for secrecy: protect those paths with a sign-in instead.",
    ),
    "wellknown:txt-": Advice(
        "The site's security.txt is missing or incomplete.",
        "Researchers who find a problem may not know whom to tell.",
        "Publish /.well-known/security.txt with a contact and a future expiry date.",
    ),
    "wellknown:": Advice(
        "A public file gives something away.",
        "Files meant for search engines and researchers are also read by attackers.",
        "Check that nothing in it is sensitive.",
    ),
    "spider:password-http": Advice(
        "A password is sent without encryption.",
        "Anyone on the network path can read it.",
        "Serve the sign-in page and its form target over https only.",
    ),
    "spider:no-csrf-token": Advice(
        "A form that changes data shows no anti-forgery token.",
        "Another site might trigger the change from a visitor's browser (CSRF).",
        "Add per-session anti-forgery tokens, or rely on SameSite cookies and test that they hold.",
    ),
    "spider:upload": Advice(
        "The site accepts file uploads.",
        "Uploads are where stored script, oversized files and path tricks usually appear.",
        "Test what types, sizes and names are accepted and where the files end up.",
    ),
    "spider:": Advice(
        "A form on the site has a weakness.",
        "Forms are where visitors hand the site data, so mistakes here are exposed.",
        "See the technical view for the form and what is missing.",
    ),
    "entropy:": Advice(
        "The session identifiers can be guessed more easily than they should.",
        "An attacker who guesses a valid one becomes that visitor.",
        "Generate session ids from a secure random source, at least 128 bits long.",
    ),
}

_BY_SEVERITY: dict[Severity, Advice] = {
    Severity.CRITICAL: Advice(
        "A tool reported a critical problem.",
        "Critical problems can usually be used right away to take over data or the site.",
        "Treat it as urgent: have an agent confirm it, and promote it to a finding if it holds.",
    ),
    Severity.HIGH: Advice(
        "A tool reported a serious problem.",
        "Serious problems can lead to data exposure or a takeover if someone uses them.",
        "Have an agent confirm it and promote it to a finding if it holds.",
    ),
    Severity.MEDIUM: Advice(
        "A tool reported a moderate problem.",
        "On its own it may not be enough to attack the site, but it helps an attacker.",
        "Check whether it can be combined with other results, and record it if it matters.",
    ),
    Severity.LOW: Advice(
        "A tool reported a minor problem.",
        "It is unlikely to be used on its own but weakens the site's defences.",
        "Fix it when convenient and note it in the report.",
    ),
    Severity.INFO: Advice(
        "A tool noticed something worth knowing.",
        "It is not a flaw, but it tells you what the site is and how it behaves.",
        "Read it for context. No action is needed.",
    ),
}


def advice_for(reference: str | None, severity: Severity) -> Advice:
    """The advice for a finding: by reference (the longest matching prefix), else by severity."""
    if reference:
        found = ADVICE.get(reference)
        if found is not None:
            return found
        prefixes = [key for key in ADVICE if reference.startswith(key)]
        if prefixes:
            return ADVICE[max(prefixes, key=len)]
    return _BY_SEVERITY[severity]
