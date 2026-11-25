import { describe, expect, it } from "vitest";
import {
  MAX_LINES,
  commandLine,
  duration,
  highlight,
  listQuery,
  rawFileName,
  rememberView,
  rememberedView,
  sectionsOf,
  withTerms,
} from "../src/results";

describe("duration", () => {
  it("says a span the way a person reads it", () => {
    expect(duration(null)).toBe("—");
    expect(duration(850)).toBe("850 ms");
    expect(duration(12_340)).toBe("12.3 s");
    expect(duration(185_000)).toBe("3 min 5 s");
  });
});

describe("commandLine", () => {
  it("quotes only the arguments a shell would split", () => {
    expect(commandLine(["nmap", "-p", "80,443", "example.com"])).toBe("nmap -p 80,443 example.com");
    expect(commandLine(["curl", "-H", "X-A: b c", "it's"])).toBe("curl -H 'X-A: b c' 'it'\\''s'");
  });
});

describe("withTerms", () => {
  const terms = [
    { term: "TLS", meaning: "Encryption for connections." },
    { term: "open port", meaning: "A door a service listens at." },
  ];

  it("marks whole-word terms in any case and keeps the text between", () => {
    expect(withTerms("The tls setup has an open port.", terms)).toEqual([
      { text: "The " },
      { text: "tls", meaning: "Encryption for connections." },
      { text: " setup has an " },
      { text: "open port", meaning: "A door a service listens at." },
      { text: "." },
    ]);
  });

  it("does not mark a term inside a longer word, and handles no terms", () => {
    expect(withTerms("Settlsx and xtls", terms)).toEqual([{ text: "Settlsx and xtls" }]);
    expect(withTerms("TLS", terms)).toEqual([
      { text: "TLS", meaning: "Encryption for connections." },
    ]);
    expect(withTerms("", terms)).toEqual([]);
  });
});

describe("sectionsOf", () => {
  it("makes a table for each list that has rows, with the columns that have values", () => {
    const sections = sectionsOf({
      issues: [{ severity: "high", title: "Weak", target: null, extra: 1 }],
      hosts: [
        {
          address: "10.0.0.1",
          state: "up",
          services: [
            { port: 80, protocol: "tcp", name: "http" },
            { port: 22, protocol: "tcp", name: "ssh" },
          ],
        },
        { address: "10.0.0.2", state: "down", services: [] },
        { address: "10.0.0.3", state: "up" },
      ],
      http: [],
      technologies: [{ name: "nginx", version: { major: 1 } }],
    });
    expect(sections.map((one) => one.key)).toEqual(["issues", "hosts", "technologies"]);
    expect(sections[0]?.headers).toEqual([
      { title: "severity", key: "severity" },
      { title: "title", key: "title" },
    ]);
    expect(sections[1]?.items).toEqual([
      { address: "10.0.0.1", port: 80, protocol: "tcp", state: "up", name: "http" },
      { address: "10.0.0.1", port: 22, protocol: "tcp", state: "up", name: "ssh" },
      { address: "10.0.0.2", port: "", protocol: "", state: "down", name: "" },
      { address: "10.0.0.3", port: "", protocol: "", state: "up", name: "" },
    ]);
    expect(sections[2]?.items).toEqual([{ name: "nginx", version: '{"major":1}' }]);
  });

  it("makes nothing from an empty result", () => {
    expect(sectionsOf({})).toEqual([]);
  });
});

describe("highlight", () => {
  it("colours tags, keys, strings and numbers and loses no text", () => {
    const text = '<port protocol="tcp">80</port>\n{"name": "x\\"y", "n": -1.5}\nplain 22';
    const shown = highlight(text, "");
    expect(shown.matches).toBe(0);
    expect(shown.hiddenLines).toBe(0);
    expect(shown.lines.map((line) => line.map((token) => token.text).join(""))).toEqual(
      text.split("\n"),
    );
    const kinds = new Set(shown.lines.flat().map((token) => token.kind));
    expect([...kinds].sort()).toEqual(["key", "number", "plain", "string", "tag"]);
  });

  it("treats an unclosed quote as plain text", () => {
    const shown = highlight('say "unfinished', "");
    expect(shown.lines[0]).toEqual([{ text: 'say "unfinished', kind: "plain" }]);
  });

  it("marks what was searched for, in any case, and counts it", () => {
    const shown = highlight('Server: nginx\n"nginx" NGINX', "nginx");
    expect(shown.matches).toBe(3);
    const marked = shown.lines.flat().filter((token) => token.kind === "match");
    expect(marked.map((token) => token.text)).toEqual(["nginx", "nginx", "NGINX"]);
  });

  it("keeps a token with no match whole and the text after the last match", () => {
    const shown = highlight("abc xyz abc!", "abc");
    expect(shown.lines[0]?.map((token) => token.text)).toEqual(["abc", " xyz ", "abc", "!"]);
    expect(highlight("no hit here", "zzz").lines[0]).toEqual([
      { text: "no hit here", kind: "plain" },
    ]);
  });

  it("makes only the first lines of a very long output", () => {
    const shown = highlight("x\n".repeat(MAX_LINES + 5), "");
    expect(shown.lines).toHaveLength(MAX_LINES);
    expect(shown.hiddenLines).toBe(6);
  });
});

describe("rawFileName", () => {
  it("makes a plain name from the title", () => {
    expect(rawFileName({ title: "Nmap: 10.0.0.1 / web!", tool_id: "p.nmap" })).toBe(
      "p.nmap-nmap-10-0-0-1-web.txt",
    );
    expect(rawFileName({ title: "???", tool_id: null })).toBe("result-output.txt");
  });
});

describe("listQuery", () => {
  const none = {
    view: "live" as const,
    q: " ",
    tool: null,
    agent: null,
    severity: null,
    test: "",
    offset: 0,
  };

  it("holds only what is set", () => {
    expect(listQuery(none)).toBe("view=live&limit=50");
    expect(
      listQuery({
        view: "trash",
        q: " nginx ",
        tool: "p.nmap",
        agent: "recon",
        severity: "high",
        test: " WSTG-1 ",
        offset: 50,
      }),
    ).toBe(
      "view=trash&limit=50&q=nginx&tool=p.nmap&agent=recon&severity=high&test=WSTG-1&offset=50",
    );
  });
});

describe("the remembered view", () => {
  it("is friendly until a person picks, then theirs, and ignores nonsense", () => {
    expect(rememberedView("u-1")).toBe("friendly");
    rememberView("u-1", "raw");
    expect(rememberedView("u-1")).toBe("raw");
    expect(rememberedView("u-2")).toBe("friendly");
    localStorage.setItem("blindspot.results-view.u-3", "sideways");
    expect(rememberedView("u-3")).toBe("friendly");
  });
});
