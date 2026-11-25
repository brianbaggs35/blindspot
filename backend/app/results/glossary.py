"""Plain-words meanings of the terms a result uses, shown as tooltips on the friendly view."""

import re

GLOSSARY: dict[str, str] = {
    "port": (
        "A numbered door on a server. Each service (the website, email, a database) listens on its"
        " own."
    ),
    "TLS": "The encryption that turns http into https and keeps a connection private.",
    "certificate": "A document that proves a website is who it says it is, so browsers trust it.",
    "HSTS": "A header that tells browsers to always use https for a site and never plain http.",
    "CSP": (
        "A header that lists where a page may load script from, which stops most injected script."
    ),
    "CORS": (
        "The rules for which other websites may read a site's answers from a visitor's browser."
    ),
    "CSRF": "A trick that makes a signed-in visitor's browser send a request they did not choose.",
    "XSS": "Injecting script into a page so it runs in other visitors' browsers.",
    "SQL injection": "Sending database commands through a form or address so the site runs them.",
    "JWT": "A signed login token. Anyone who holds a valid one is treated as the person it names.",
    "cookie": (
        "A small value a site asks the browser to keep and send back, often to remember a login."
    ),
    "HttpOnly": "A cookie setting that hides the cookie from script on the page.",
    "SameSite": (
        "A cookie setting that stops the cookie travelling with requests started by other sites."
    ),
    "Secure": "A cookie setting that keeps the cookie off unencrypted connections.",
    "banner": "The name and version a service announces about itself.",
    "WAF": (
        "A web application firewall: a filter in front of a site that blocks attack-like requests."
    ),
    "robots.txt": "A public file that asks search engines to skip some paths. It protects nothing.",
    "sitemap": "A public list of a site's pages, written for search engines.",
    "security.txt": "A public file that tells researchers how to report a problem.",
    "entropy": "How unpredictable a value is. Low entropy means it can be guessed.",
    "clickjacking": "Hiding a site in a frame so a visitor clicks something they cannot see.",
    "redirect": "An answer that sends the browser to another address.",
    "header": "A line of extra information that comes with every web response.",
}


def terms_in(*texts: str) -> list[dict[str, str]]:
    """The glossary entries whose term appears in the texts, in the order of the glossary."""
    haystack = " ".join(texts)
    return [
        {"term": term, "meaning": meaning}
        for term, meaning in GLOSSARY.items()
        if re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", haystack, re.IGNORECASE)
    ]
