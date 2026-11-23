# WSTG test-by-test tool map

Every one of the 133 tests in the OWASP WSTG checklist (verified against `checklists/checklist.json`: 13 categories) is mapped to the tools that can do it. The mapping is data, not code: it lives in `methodologies/wstg/tools.yaml` and the Tools settings page reads it, so a new methodology ships its own map in the same format. A build-time check fails if any test in a methodology has no tool or no `manual-review` fallback.

Versions and dates were read on 2026-11-23 from PyPI, npm, the Go module proxy, the Wolfi package index, Docker Hub / GHCR tag lists and `git ls-remote` against each project. Star counts could not be read yet (the GitHub API is outside this session's allow-list; `api.deps.dev` has been requested), so the adoption column in the vetting table is marked pending rather than guessed.

## How to read it

| Tier | Meaning | Run modes on the Tools page |
| --- | --- | --- |
| **B** Built-in | Python code inside Blindspot. No binary, no image | in-process (always) |
| **C** Core | Packaged in Wolfi and bundled in the app image | local (in the container) or Docker |
| **P** Pack | Not in Wolfi or newer than Wolfi has. Built by our release pipeline into signed pack images, or installed from a pinned, checksummed release into `/data/tools` | Docker or installed |
| **O** Optional | Licensing or weight means we do not ship it. The Tools page offers a one-click pull of the project's own official image | Docker |

Risk classes follow the plan: passive, active, intrusive, destructive. Nothing here is destructive by default.

## Tool registry (60 entries)

| ID | Tool | Tier | Source and verified version | Risk | Notes |
| --- | --- | --- | --- | --- | --- |
| `b.http` | Scoped HTTP client + raw capture | B | aiohttp 3.14.5 (2026-10-11), h2 4.4.1 (2026-08-03) | passive | Every request passes the scope guard; stores raw request/response. HTTP/1.1 and HTTP/2 |
| `b.browser` | Instrumented browser | B | Playwright 1.65.2 PyPI (2026-11-14), Chromium 149 (Wolfi) | active | DOM sink hooks, storage/service-worker/WebSocket/SSE/postMessage capture, HAR, screenshots |
| `b.osint` | Passive OSINT sources | B | crt.sh, Wayback CDX, Common Crawl index, search APIs you configure | passive | No scan traffic reaches the target |
| `b.dns` | DNS and takeover checks | B | dnspython 2.9.2 (2026-11-03), tldextract 5.4.0 | passive | Records, dangling CNAME/NS fingerprints, zone-transfer attempt (active) |
| `b.tls` | TLS audit (library) | B | sslyze 6.3.1 (2026-03-29) | active | Protocols, ciphers, certs, HSTS, renegotiation, Heartbleed, ROBOT |
| `b.headers` | Header, cookie, CSP, CORS, cache analyzers | B | stdlib + our rule sets | passive | CSP evaluator, HSTS preload, cookie flags, CORS reflection/credentials, Cache-Control |
| `b.spider` | Crawler and parameter/form mapper | B | selectolax 1.0.2 (2026-10-22), lxml 6.1.3, b.browser | active | Sitemaps, robots, forms, JS routes, API calls seen in the browser |
| `b.params` | Hidden parameter and path discovery | B | own implementation, wordlists | active | Replaces Arjun (last release 2024-11) and Burp Param Miner |
| `b.jwt` | JWT analyzer | B | PyJWT 2.15.1 (2026-09-28), jwcrypto 1.6.1 (2026-09-15) | active | alg none, key confusion, weak HMAC secret, kid/jku/x5u abuse, expiry; replaces jwt_tool (last commit 2025-05) |
| `b.saml` | SAML analyzer | B | signxml 5.3.1 (2026-11-22), pysaml2 7.5.5 (2026-09-17) | active | Signature wrapping, comment injection, replay, audience/recipient checks |
| `b.oidc` | OAuth 2 / OpenID Connect analyzer | B | Authlib 1.9.10 (2026-11-20), oauthlib 4.0.1 (2026-10-31) | active | Discovery, redirect_uri, state, nonce, PKCE, implicit flow, token leakage |
| `b.webauthn` | Passkey / WebAuthn analyzer | B | webauthn 3.0.1 (2026-09-25), browser virtual authenticator | active | rpId/origin checks, challenge reuse, UV enforcement, fallback paths |
| `b.session` | Session analyzer | B | b.http + b.browser + our entropy tests (entropy estimation) | active | Token entropy, fixation, logout, timeout, concurrency, cookie scope |
| `b.csrf` | CSRF tester | B | b.browser (cross-origin form and fetch replay) | active | Token presence/validation, SameSite, Origin checks, JSON content-type tricks |
| `b.race` | Race-condition engine | B | h2 4.4.1 (single-packet technique) | intrusive | Parallel requests released in one TCP packet; limit/coupon/transfer tests |
| `b.smuggle` | HTTP desync prober | B | raw sockets + h2 4.4.1 | intrusive | CL.TE, TE.CL, H2.CL, H2.TE, TE obfuscation; timing and differential detection. Replaces smuggler (2021) and h2csmuggler (2020); PortSwigger HTTP Request Smuggler is a Burp extension |
| `b.cache` | Web cache probe | B | b.http | intrusive | Unkeyed header/param discovery, cache poisoning and deception with unique cache busters |
| `b.inject` | Injection probe set | B | b.http + b.oast | intrusive | Host header, CRLF/response splitting, SSI, XPath, LDAP, XML/XXE, IMAP/SMTP, format string, CSV, HPP, JSON-parser differentials, Unicode normalization, mass assignment, prototype pollution (server), SSTI detection, SSRF detection |
| `b.redirect` | Redirect tester | B | b.http + b.browser | active | Server-side and client-side open redirect |
| `b.upload` | Upload tester | B | b.http, EICAR test string | intrusive | Extension/content-type/magic-byte/polyglot/size/zip-bomb-safe checks; never uploads real malware |
| `b.graphql` | GraphQL analyzer | B | graphql-core 3.3.2 (2026-11-06) | active | Introspection, suggestions, batching/alias/depth limits, field-level authorization |
| `b.openapi` | OpenAPI importer | B | openapi-spec-validator 0.9.0 (2026-05-20), prance 26.7.19.0 | passive | Spec to endpoint inventory |
| `b.ws` | WebSocket/SSE tester | B | websockets 17.4 (2026-10-30) | active | Origin checks (CSWSH), auth, message tampering, SSE auth/CORS |
| `b.grpc` | gRPC tester | B | grpcio-reflection + grpcurl | active | Reflection, auth, metadata, message fuzz |
| `b.padding` | Padding-oracle detector | B | cryptography 50.0.2 | active | Detection only (CBC response differential); exploitation off. padding-oracle on PyPI last released 2023-11 |
| `b.redos` | ReDoS analyzer | B | redos-detector 6.1.4 (npm, 2026-02-14) + bounded timing probes | active | Replaces regexploit (last commit 2021-05) |
| `b.jsstatic` | JavaScript static analysis | B | acorn 8.19.0, @babel/parser 8.1.3, webcrack 2.16.0, Semgrep | passive | Sinks, hidden routes, secrets, source maps, prototype-pollution gadgets, postMessage handlers |
| `b.wasm` | WebAssembly analyzer | B | wabt 1.0.42 / wasm-tools 1.263.0 / binaryen 133 (Wolfi), wasmtime 51.0.0 (PyPI, 2026-11-20) | passive | Extract modules, disassemble, imports/exports, sandboxed execution |
| `b.oast` | Out-of-band listener (OAST) | B | built-in DNS/HTTP listener; interactsh-client 1.4.1 (2026-09-30) optional | active | Blind SSRF/XXE/injection. Public OAST servers are OFF by default (data would leave the machine) |
| `c.nmap` | Nmap | C | Wolfi nmap 7.94 | active | Ports, services, NSE scripts (http-*, ssl-*, vulners excluded: CVE enrichment is ours) |
| `c.nuclei` | Nuclei + community templates | C | Wolfi nuclei 3.11.1 (matches Go proxy v3.11.1, 2026-08-08) | active | Templates tagged by risk; DAST/fuzz templates are intrusive |
| `c.sqlmap` | sqlmap | C | Wolfi sqlmap 1.10 (PyPI 1.10.11, 2026-10-30) | intrusive | Always asks; level/risk capped per pentest |
| `c.gobuster` | gobuster | C | Wolfi gobuster 3.8.2 | active | dir/dns/vhost modes |
| `c.amass` | OWASP Amass | C | Wolfi amass 5.1.3 (Go proxy v5.1.3, 2026-10-25) | passive | Attack-surface mapping, passive by default |
| `c.hydra` | THC Hydra | C | Wolfi hydra 26.2.0 | intrusive | Credential testing; lockout-aware, always asks |
| `c.base` | openssl + curl + dig | C | Wolfi openssl 3.6.5, curl 8.23.0, bind-tools 9.20.31 | passive | Primitives used by built-ins |
| `c.whitebox` | Semgrep, Gitleaks, OSV-Scanner, Trivy, Syft, Grype | C | Wolfi semgrep 1.165.0 (PyPI has 1.186.0), gitleaks 8.30.1, osv-scanner 2.7.1, trivy 0.70.0, syft 1.57.2, grype 0.122.1 | passive | Source, dependency, secret, IaC, SBOM scans (white box) |
| `c.wasmtools` | WABT, wasm-tools, Binaryen, Wasmtime | C | Wolfi wabt 1.0.42, wasm-tools 1.263.0, binaryen 133, wasmtime 45.0.1 | passive |  |
| `c.grpcurl` | grpcurl | C | Wolfi grpcurl 1.9.4 | active |  |
| `c.trufflehog` | TruffleHog | C | Wolfi trufflehog 3.95.5 (Go proxy has 3.100.0) | passive | AGPL-3.0: run as a separate process, not linked |
| `p.pd` | ProjectDiscovery recon | P | subfinder 2.17.0, dnsx 1.3.1, httpx 1.12.0, katana 1.8.0, tlsx 1.5.0, naabu 2.7.0, cdncheck 1.4.0 (Go proxy, 2026-08..11) | active | Fast resolution, probing, JS-aware crawl, TLS, ports. Built from pinned tags |
| `p.ffuf` | ffuf | P | ffuf 2.3.0 (Go proxy, 2026-09-09) | active | Content, vhost and parameter fuzzing |
| `p.dalfox` | Dalfox | P | dalfox 3.3.0 (rewritten in Rust; git tag v3.3.0; last commit 2026-11-23) | intrusive | XSS scanning with DOM/AST verification. The Go-proxy v2.13.0 is the old line, not used |
| `p.testssl` | testssl.sh | P | testssl.sh pinned commit (last commit 2026-11-20, snapshot tag v3.3dev-snapshot-2611) | active | Second opinion to sslyze, report parity with the usual tooling |
| `p.waf` | wafw00f | P | wafw00f 2.4.2 (PyPI, 2026-01-26) | active | WAF fingerprinting |
| `p.commix` | commix | P | commix 4.1 (git tag v4.1; last commit 2026-11-23; PyPI is stale at 0.1 from 2022) | intrusive | Command injection; install from git tag |
| `p.sstimap` | SSTImap | P | SSTImap 1.4 (git tag; last commit 2026-08-26) | intrusive | Template injection |
| `p.403` | nomore403 | P | nomore403 v2.0.1 (git; last commit 2026-10-30) | active | Access-control bypass variations |
| `p.retire` | Retire.js | P | retire 6.1.1 (npm, 2026-11-11) | passive | Vulnerable JavaScript libraries |
| `p.graphql` | graphql-cop, graphw00f, clairvoyance | P | graphql-cop 1.16 (last commit 2025-11-07), graphw00f 1.2.1, clairvoyance 2.5.5 (PyPI, 2025-12-05) | active | Engine fingerprint, misconfig checks, schema recovery when introspection is off |
| `p.schemathesis` | Schemathesis | P | schemathesis 4.34.0 (PyPI, 2026-11-22) | intrusive | Spec-driven API fuzzing and stateful tests |
| `p.osint` | theHarvester, cloud_enum, S3Scanner | P | theHarvester (last commit 2026-11-21), cloud_enum (2026-10-04), S3Scanner (Go, 2026-07-14), pinned commits | passive | Email/host OSINT; public cloud bucket discovery |
| `p.ysoserial` | ysoserial (+ .NET and PHP equivalents) | P | ysoserial (last commit 2025-12-03, no versioned releases, pin commit), JDK 21 (Wolfi) | intrusive | Gadget payloads for deserialization checks; off unless the stack is detected; payloads are safe canaries (DNS callback), not shells |
| `p.checkov` | Checkov | P | checkov 3.4.6 (PyPI, 2026-11-19) | passive | IaC scanning (white box) |
| `p.wapiti` | Wapiti | P | wapiti3 3.3.4 (PyPI, 2026-11-22; last commit 2026-11-23) | intrusive | Black-box DAST second opinion (XSS, SQLi, XXE, SSRF, CRLF, file inclusion) |
| `p.zap` | OWASP ZAP | P | official image ghcr.io/zaproxy/zaproxy (tags stable, weekly, latest verified; weekly git tag w2026-11-19) | intrusive | Optional heavy engine: spider, AJAX spider, active scan, API scan. Driven through its API |
| `o.nikto` | Nikto | O | nikto 2.5.x; official image ghcr.io/sullo/nikto. Code is GPL-3 but the database files may only be distributed with the official package | active | Not redistributed by Blindspot: you pull the official image yourself (Tools page offers it). Source repo shows a "pro cutover" tag from 2026-02 |
| `o.whatweb` | WhatWeb | O | WhatWeb 0.6.4 (git tag; last commit 2026-04-03) | active | Fingerprinting; httpx -tech-detect covers most of it |
| `o.searxng` | SearXNG (self-hosted search) | O | official image searxng/searxng | passive | Search-engine recon without a paid API; or bring your own Brave/Bing/Google API key |
| `o.ref` | Custom tools / MCP servers | O | your own | varies | Same manifest, scope guard, permissions and audit as the rest |

## Test-by-test map (133 tests)

### Information Gathering (9)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-INFO-01 | Conduct Search Engine Reconnaissance for Information Leakage | `b.osint`, `p.osint`, `o.searxng` | Search-engine dorks, cached/archived pages, public code and paste sites; passive |
| WSTG-INFO-02 | Fingerprint Web Server | `b.http`, `p.pd`, `c.nmap` | Banner, header ordering and error-page fingerprints; nmap -sV |
| WSTG-INFO-03 | Review Webserver Metafiles for Information Leakage | `b.http`, `b.spider` | robots.txt, sitemap.xml, security.txt, humans.txt, meta tags |
| WSTG-INFO-04 | Attack Surface Identification | `c.amass`, `p.pd`, `b.dns`, `c.nmap`, `b.osint` | Subdomains, ports, virtual hosts, certificates (CT logs), cloud assets |
| WSTG-INFO-05 | Review Web Page Content for Information Leakage | `b.spider`, `b.jsstatic`, `c.whitebox`, `c.trufflehog` | Comments, metadata, source maps, secrets in JS; Gitleaks on supplied source |
| WSTG-INFO-06 | Identify Application Entry Points | `b.spider`, `b.browser`, `b.params` | Forms, parameters, headers, cookies, API calls seen in the browser |
| WSTG-INFO-07 | Map Execution Paths Through Application | `b.browser`, `b.spider`, `p.zap` | Authenticated and unauthenticated crawl, state graph of pages and flows |
| WSTG-INFO-08 | Fingerprint Web Application Framework | `p.pd`, `o.whatweb`, `p.retire`, `b.http` | Framework and CMS fingerprints, library versions |
| WSTG-INFO-09 | Map Application Architecture | `b.http`, `p.waf`, `b.dns`, `p.pd` | CDN, WAF, load balancer, proxies, backends; hand-off to the architecture graph |

### Configuration and Deployment Management (14)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-CONF-01 | Network Infrastructure Configuration | `c.nmap`, `b.tls`, `b.headers` | Exposed services, management ports, server config |
| WSTG-CONF-02 | Application Platform Configuration | `c.nuclei`, `b.http`, `p.wapiti`, `o.nikto` | Default pages, debug endpoints, known misconfigs (templates) |
| WSTG-CONF-03 | Review Old Backup and Unreferenced Files for Sensitive Information | `p.ffuf`, `c.gobuster`, `c.nuclei`, `b.http`, `o.nikto` | Backup, old, temp and unreferenced files; exposed .git/.env |
| WSTG-CONF-04 | Enumerate Infrastructure and Application Admin Interfaces | `p.ffuf`, `c.nuclei`, `p.403`, `b.http` | Admin paths and consoles, then access-control bypass variations |
| WSTG-CONF-05 | HTTP Methods | `b.http`, `c.nmap` | OPTIONS, TRACE, PUT/DELETE probes (destructive methods only against test resources you name) |
| WSTG-CONF-06 | HTTP Strict Transport Security | `b.headers`, `b.tls` | HSTS presence, max-age, includeSubDomains, preload |
| WSTG-CONF-07 | File Permissions | `c.whitebox`, `p.checkov` | File permissions in source/containers (white box); black box: exposed file listing |
| WSTG-CONF-08 | Subdomain Takeover | `b.dns`, `c.nuclei`, `p.pd` | Dangling CNAME/NS/A records against provider fingerprints. Replaces dnsReaper (last commit 2025-10) |
| WSTG-CONF-09 | Cloud Storage | `p.osint`, `c.nuclei`, `b.http` | Public bucket discovery and ACL checks (read-only) |
| WSTG-CONF-10 | Content Security Policy | `b.headers`, `b.browser` | CSP evaluation and violation reports |
| WSTG-CONF-11 | Path Confusion | `b.http`, `b.cache`, `c.nuclei` | Path confusion, delimiter and normalization differences |
| WSTG-CONF-12 | Additional Browser Security Controls | `b.headers`, `b.browser` | Referrer-Policy, Permissions-Policy, COOP/COEP/CORP, X-Content-Type-Options |
| WSTG-CONF-13 | Feature Flag Security Bypass | `b.jsstatic`, `b.http`, `b.browser` | Client-side flag stores, flag endpoints, bypass attempts |
| WSTG-CONF-14 | Web Cache Poisoning | `b.cache`, `b.params` | Unkeyed inputs, poisoning and deception with cache busters |

### Identity Management (5)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-IDNT-01 | Role Definitions | `b.http`, `b.browser` | Role matrix from docs and observed behavior (grey/white box) |
| WSTG-IDNT-02 | User Registration Process | `b.browser`, `b.http` | Registration rules, validation, duplicates, self-assigned roles |
| WSTG-IDNT-03 | Account Provisioning Process | `b.browser`, `b.http` | Provisioning and approval flows, privilege of new accounts |
| WSTG-IDNT-04 | Account Enumeration and Guessable User Account | `b.http`, `b.session` | Response, timing and error differences for valid vs invalid users |
| WSTG-IDNT-05 | Email Address Verification | `b.http`, `b.browser` | Verification link entropy, reuse, expiry, bypass |

### Authentication (13)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-ATHN-01 | Default Credentials | `c.nuclei`, `c.hydra`, `b.http` | Vendor default-credential templates; tiny, rate-limited, approval required |
| WSTG-ATHN-02 | Weak Lock Out Mechanism | `b.http`, `c.hydra` | Lockout thresholds measured with throwaway accounts |
| WSTG-ATHN-03 | Bypassing Authentication Schema | `b.http`, `b.browser`, `p.403` | Forced browsing, parameter tampering, direct page access |
| WSTG-ATHN-04 | Vulnerable Remember Password | `b.browser`, `b.session` | Remember-me tokens, autocomplete, storage |
| WSTG-ATHN-05 | Browser Cache Weaknesses | `b.headers`, `b.browser` | Cache-Control on authenticated pages, back-button and storage leakage |
| WSTG-ATHN-06 | Weak Authentication Methods | `b.http`, `b.browser` | Weak auth methods, basic auth, password policy |
| WSTG-ATHN-07 | Weak Security Question Answer | `b.http`, `b.browser` | Security-question flows |
| WSTG-ATHN-08 | Weak Password Change or Reset Functionalities | `b.http`, `b.browser`, `b.oast` | Reset token entropy/expiry/reuse, host-header poisoning of reset links |
| WSTG-ATHN-09 | Weaker Authentication in Alternative Channel | `b.http`, `b.browser` | Mobile/API/legacy endpoints with weaker checks |
| WSTG-ATHN-10 | Multi-Factor Authentication (MFA) | `b.browser`, `b.http`, `b.session` | MFA bypass, rate limits, backup codes, enrollment flow |
| WSTG-ATHN-11 | SAML Authentication | `b.saml` | SAML signature, replay and binding checks |
| WSTG-ATHN-12 | Passkeys and WebAuthn | `b.webauthn`, `b.browser` | Virtual authenticator tests, fallbacks |
| WSTG-ATHN-13 | OpenID Connect Relying Party | `b.oidc` | OIDC relying-party checks |

### Authorization (5)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-ATHZ-01 | Directory Traversal and File Include | `b.http`, `c.nuclei`, `b.inject` | Traversal and file-include payload families with encoding variants |
| WSTG-ATHZ-02 | Bypassing Authorization Schema | `b.http`, `b.session`, `p.403` | Replay each request as other roles and as anonymous |
| WSTG-ATHZ-03 | Privilege Escalation | `b.http`, `b.session` | Role/parameter tampering across the role matrix |
| WSTG-ATHZ-04 | Insecure Direct Object References | `b.http`, `b.session` | Object-id swapping between two accounts (grey box) |
| WSTG-ATHZ-05 | OAuth Weaknesses | `b.oidc` | OAuth 2 flow checks |

### Session Management (11)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-SESS-01 | Session Management Schema | `b.session`, `b.http` | Token entropy, structure, rotation |
| WSTG-SESS-02 | Cookies Attributes | `b.headers`, `b.browser` | Secure, HttpOnly, SameSite, Domain, Path, prefixes |
| WSTG-SESS-03 | Session Fixation | `b.session` | Token before and after login |
| WSTG-SESS-04 | Exposed Session Variables | `b.http`, `b.browser` | Tokens in URLs, logs, referrers, storage |
| WSTG-SESS-05 | Cross Site Request Forgery | `b.csrf` | Cross-origin replay of state-changing requests |
| WSTG-SESS-06 | Logout Functionality | `b.session`, `b.browser` | Server-side invalidation after logout |
| WSTG-SESS-07 | Session Timeout | `b.session` | Idle and absolute timeouts |
| WSTG-SESS-08 | Session Puzzling | `b.session`, `b.http` | Cross-flow variable reuse |
| WSTG-SESS-09 | Session Hijacking | `b.session`, `b.headers` | Transport and cookie scope; no interception is performed |
| WSTG-SESS-10 | JSON Web Tokens | `b.jwt` | JWT analyzer |
| WSTG-SESS-11 | Concurrent Sessions | `b.session` | Parallel logins and token behavior |

### Injection (27)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-INJT-01 | Reflected Cross Site Scripting | `p.dalfox`, `b.browser`, `p.wapiti`, `p.zap`, `b.oast` | Reflection context analysis, then browser-verified payloads |
| WSTG-INJT-02 | Stored Cross Site Scripting | `p.dalfox`, `b.browser`, `b.oast` | Write then revisit with unique markers; browser-verified |
| WSTG-INJT-03 | HTTP Parameter Pollution | `b.inject` | Duplicate-parameter handling |
| WSTG-INJT-04 | SQL Injection | `c.sqlmap`, `p.wapiti`, `p.zap`, `c.nuclei`, `b.http` | Detection first; exploitation levels need approval |
| WSTG-INJT-05 | LDAP Injection | `b.inject`, `c.nuclei` | LDAP filter metacharacter probes |
| WSTG-INJT-06 | XML Injection | `b.inject`, `b.oast` | XML/XXE, entity expansion (bounded), SOAP |
| WSTG-INJT-07 | SSI Injection | `b.inject`, `c.nuclei` | SSI directives |
| WSTG-INJT-08 | XPath Injection | `b.inject` | XPath boolean/error probes |
| WSTG-INJT-09 | IMAP SMTP Injection | `b.inject`, `b.oast` | Mail header injection |
| WSTG-INJT-10 | Code Injection | `b.inject`, `c.nuclei`, `b.oast` | Server-side evaluation probes |
| WSTG-INJT-11 | Command Injection | `p.commix`, `b.inject`, `b.oast` | Time- and OAST-based detection |
| WSTG-INJT-12 | Format String Injection | `b.inject` | Format-string probes |
| WSTG-INJT-13 | Incubated Vulnerability | `b.inject`, `b.oast`, `b.browser` | Stored payload with delayed trigger tracking |
| WSTG-INJT-14 | HTTP Response Splitting | `b.inject` | CRLF in headers and redirects |
| WSTG-INJT-15 | HTTP Request Smuggling | `b.smuggle` | Desync probes with safe differential detection |
| WSTG-INJT-16 | Host Header Injection | `b.inject`, `b.cache` | Host/X-Forwarded-Host handling, cache and reset-link poisoning |
| WSTG-INJT-17 | Server-side Template Injection | `p.sstimap`, `b.inject`, `c.nuclei` | Engine fingerprint, then bounded proof |
| WSTG-INJT-18 | Server-Side Request Forgery | `b.oast`, `b.inject`, `c.nuclei` | Callback-based detection; cloud-metadata targets blocked by default |
| WSTG-INJT-19 | Mass Assignment | `b.inject`, `b.http` | Extra-field and role-field injection |
| WSTG-INJT-20 | CSV Injection | `b.inject` | Formula injection in exports |
| WSTG-INJT-21 | Prototype Pollution | `b.inject`, `b.browser`, `b.jsstatic` | Server merge probes and client gadget search |
| WSTG-INJT-22 | Insecure Deserialization | `p.ysoserial`, `b.inject`, `b.oast`, `c.nuclei` | Format detection, canary payloads only |
| WSTG-INJT-23 | Server-side URL Redirect | `b.redirect` | Open redirect |
| WSTG-INJT-24 | Unicode Normalization and Case Mapping | `b.inject` | Normalization and case-mapping differentials |
| WSTG-INJT-25 | JSON Parser Differentials | `b.inject` | Parser differential suite (duplicate keys, comments, big numbers) |
| WSTG-INJT-26 | Server-side Document Rendering Injection | `b.oast`, `b.inject` | HTML-to-PDF and image renderers: SSRF/LFI canaries |
| WSTG-INJT-27 | Regular Expression Denial of Service | `b.redos`, `b.jsstatic` | Regex extraction then bounded timing |

### Error Handling (1)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-ERRH-01 | Improper Error Handling | `b.http`, `b.inject`, `c.nuclei` | Malformed input to trigger errors; stack-trace/secret detection |

### Weak Cryptography (4)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-CRYP-01 | Weak Transport Layer Security | `b.tls`, `p.testssl` | Protocols, ciphers, certs, known attacks |
| WSTG-CRYP-02 | Padding Oracle | `b.padding` | Detection-only oracle check |
| WSTG-CRYP-03 | Sensitive Information Sent via Unencrypted Channels | `b.http`, `b.spider`, `b.headers` | Mixed content, forms over HTTP, sensitive data in URLs |
| WSTG-CRYP-04 | Weak Cryptographic Primitives | `b.jsstatic`, `b.session`, `c.whitebox` | Weak algorithms, constants, token quality; Semgrep on source |

### Business Logic (11)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-BUSL-01 | Business Logic Data Validation | `b.http`, `b.browser` | Boundary and type abuse guided by the agent from the app model |
| WSTG-BUSL-02 | Ability to Forge Requests | `b.http`, `b.session` | Hidden-field and request forging checks |
| WSTG-BUSL-03 | Integrity Checks | `b.http`, `b.browser` | Tamper with signed/checked values |
| WSTG-BUSL-04 | Process Timing | `b.race`, `b.http` | Timing windows |
| WSTG-BUSL-05 | Number of Times a Function Can Be Used Limits | `b.race` | Limit bypass with parallel requests |
| WSTG-BUSL-06 | Circumvention of Work Flows | `b.browser`, `b.http` | Skip/reorder workflow steps |
| WSTG-BUSL-07 | Defenses Against Application Misuse | `b.http`, `b.session` | Abuse detection and rate controls |
| WSTG-BUSL-08 | Upload of Unexpected File Types | `b.upload` | Allowed and disallowed type handling |
| WSTG-BUSL-09 | Upload of Malicious Files | `b.upload` | EICAR and benign polyglots only |
| WSTG-BUSL-10 | Payment Functionality | `b.browser`, `b.http` | Test-mode payment flows only, with explicit scope |
| WSTG-BUSL-11 | Denial of Inventory | `b.race`, `b.http` | Cart/hold exhaustion on a test item, bounded |

### Client-side (20)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-CLNT-01 | DOM-Based Cross Site Scripting | `b.browser`, `b.jsstatic`, `p.dalfox` | Source-to-sink taint tracing in a real browser |
| WSTG-CLNT-02 | JavaScript Execution | `b.browser`, `b.jsstatic` | Dynamic code execution sinks |
| WSTG-CLNT-03 | HTML Injection | `b.browser`, `b.inject` | Unsanitized HTML rendering |
| WSTG-CLNT-04 | Client-side URL Redirect | `b.redirect`, `b.browser` | DOM-based redirect |
| WSTG-CLNT-05 | CSS Injection | `b.browser`, `b.inject` | CSS injection and data exfil via selectors |
| WSTG-CLNT-06 | Client-side Resource Manipulation | `b.browser`, `b.jsstatic` | Attacker-controlled resource URLs |
| WSTG-CLNT-07 | Cross Origin Resource Sharing | `b.headers`, `b.http` | Reflected/null origins, credentials, preflight handling |
| WSTG-CLNT-08 | Clickjacking | `b.headers`, `b.browser` | Frame-ancestors/X-Frame-Options, framed-page proof screenshot |
| WSTG-CLNT-09 | WebSockets | `b.ws`, `b.browser` | Origin, auth, message injection |
| WSTG-CLNT-10 | Web Messaging | `b.browser`, `b.jsstatic` | postMessage origin checks and handlers |
| WSTG-CLNT-11 | Browser Storage | `b.browser` | localStorage, sessionStorage, IndexedDB, cache contents |
| WSTG-CLNT-12 | Cross Site Script Inclusion | `b.http`, `b.browser` | Script inclusion of authenticated data cross-origin |
| WSTG-CLNT-13 | Reverse Tabnabbing | `b.spider`, `b.browser` | target=_blank without noopener |
| WSTG-CLNT-14 | Client-side Template Injection | `b.browser`, `b.jsstatic` | Framework template sinks (AngularJS, Vue) |
| WSTG-CLNT-15 | DOM Clobbering | `b.browser`, `b.jsstatic` | Named-element clobbering of globals |
| WSTG-CLNT-16 | Cross-Site Leaks | `b.browser`, `b.headers` | Cross-site leak oracles, COOP/COEP |
| WSTG-CLNT-17 | Client-side Path Traversal | `b.browser`, `b.jsstatic` | Client-side path traversal in fetch paths |
| WSTG-CLNT-18 | Service Workers | `b.browser`, `b.jsstatic` | Service-worker scope, caching, importScripts |
| WSTG-CLNT-19 | DNS Rebinding | `b.dns`, `b.http` | Host validation against rebinding |
| WSTG-CLNT-20 | Server-Sent Events | `b.ws` | SSE auth, CORS, event injection |

### API Testing (10)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-APIT-01 | API Reconnaissance | `b.openapi`, `b.browser`, `b.params`, `p.ffuf` | Spec import, traffic-derived endpoints, versions, docs endpoints |
| WSTG-APIT-02 | API Broken Object Level Authorization | `b.http`, `b.session`, `p.schemathesis` | Two-account object swap (grey box) |
| WSTG-APIT-03 | Excessive Data Exposure | `b.http`, `b.session` | Response fields vs UI needs |
| WSTG-APIT-04 | API Broken Function Level Authorization | `b.http`, `b.session`, `p.403` | Function calls across roles |
| WSTG-APIT-05 | Testing API Authentication Mechanisms | `b.jwt`, `b.oidc`, `b.http` | API keys, bearer tokens, token lifecycle |
| WSTG-APIT-06 | API Rate Limiting and Resource Consumption | `b.http`, `b.race`, `p.schemathesis` | Rate limits, pagination caps, expensive queries |
| WSTG-APIT-07 | API Mass Assignment | `b.inject`, `p.schemathesis` | Field injection from schema |
| WSTG-APIT-09 | Inbound Webhooks | `b.http`, `b.oast` | Signature validation, replay, SSRF via callbacks |
| WSTG-APIT-10 | gRPC | `b.grpc`, `c.grpcurl` | Reflection and method fuzz |
| WSTG-APIT-99 | GraphQL | `b.graphql`, `p.graphql` | Introspection, batching, depth, authorization |

### WebAssembly Testing (3)

| Test | Name | Tools | Approach |
| --- | --- | --- | --- |
| WSTG-WASM-01 | WebAssembly Reconnaissance | `b.wasm`, `b.browser` | Find and extract modules and loaders |
| WSTG-WASM-02 | WebAssembly Static Analysis | `b.wasm`, `c.wasmtools` | Decompile, imports/exports, memory |
| WSTG-WASM-03 | WebAssembly Dynamic Analysis | `b.wasm`, `b.browser` | Instrumented execution and fuzzed exports |

## Rejected or replaced (stale, unmaintained, or not redistributable)

| Candidate | Why not | Replacement |
| --- | --- | --- |
| jwt_tool | last commit 2025-05 | `b.jwt` with PyJWT and jwcrypto |
| Corsy | last commit 2021-11 | `b.headers` CORS analyzer |
| smuggler, h2csmuggler | last commits 2021-04 and 2020-09 | `b.smuggle` |
| HTTP Request Smuggler, Param Miner, DOM Invader | Burp Suite extensions, not usable outside Burp | `b.smuggle`, `b.params`, `b.browser` |
| regexploit | last commit 2021-05 | `b.redos` (redos-detector 6.1.4) |
| kiterunner | last Go release 2021-04 | `b.openapi`, `b.params`, ffuf |
| waybackurls | last release 2022-04 | `b.osint` Wayback CDX client |
| gau | last release 2024-10 | `b.osint` (Wayback, Common Crawl) |
| gospider, crlfuzz, gf | last releases 2021-06, 2020-12, 2020-06 | katana, `b.inject`, Semgrep |
| dnsReaper | last commit 2025-10 | `b.dns` plus Nuclei takeover templates |
| Arjun | last release 2024-11 | `b.params` |
| S3Scanner (PyPI), commix (PyPI), theHarvester (PyPI) | PyPI releases from 2021, 2022 and 2019 (the projects are alive on GitHub) | install from pinned git tags or commits |
| padding-oracle (PyPI) | last release 2023-11 | `b.padding` |
| esprima | last release 2018-07 | acorn, @babel/parser |
| python-Wappalyzer, wad, sublist3r, dnsrecon | last releases 2020 to 2021 | httpx `-tech-detect`, Amass, `b.dns` |
| Nikto (bundled) | database files may only be distributed with the official package | `o.nikto`: user pulls the official image |

## Gaps that need a human or the AI, not a tool

Some WSTG tests are judgement work: business logic (BUSL-01 to 07, 10, 11), identity design (IDNT-01 to 03), session puzzling and workflow circumvention. Blindspot gives the agent the browser, the HTTP client, the race engine and the role matrix, and marks the result `needs-review` rather than pretending a scanner covered it. The checklist page shows which tests were covered by tools, by the agent only, or not at all.
