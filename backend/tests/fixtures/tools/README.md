# Tool output fixtures

`nmap.xml`, `nmap-closed.xml`, `ffuf.json`, `whatweb.json`, `wafw00f.json`, `testssl.json` and
`nikto.csv` are real output: each was captured on 2026-11-25 by running the tool (Ubuntu 24.04
packages: nmap 7.94, ffuf 2.1.0, WhatWeb 0.5.5, wafw00f 2.2.0, testssl.sh 3.2rc3, Nikto 2.1.5)
against a small web server on 127.0.0.1 (Apache-like banner, PHP cookie, a self-signed
certificate on the second port).

`nuclei.jsonl` and `httpx.jsonl` are written by hand from the formats those tools document
(ProjectDiscovery's releases cannot be downloaded in the build environment), with the kinds of
noise they print (a banner line, a line that is JSON but not a result). Replace them with captured
output when the Docker runner (BLI-24) can run the tools.

`golden/` holds what each parser makes of each fixture. After changing a parser on purpose, run
`BLINDSPOT_UPDATE_GOLDEN=1 uv run pytest tests/test_tools_parsers.py` and read the diff.
