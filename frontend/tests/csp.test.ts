import { afterEach, describe, expect, it } from "vitest";
import { cspNonce } from "../src/csp";

function setNonceMeta(content?: string) {
  document.head.innerHTML =
    content === undefined ? "" : `<meta name="csp-nonce" content="${content}" />`;
}

describe("cspNonce", () => {
  afterEach(() => {
    document.head.innerHTML = "";
  });

  it("reads the nonce nginx put in the page", () => {
    setNonceMeta("a1b2c3");
    expect(cspNonce()).toBe("a1b2c3");
  });

  it("has none while the placeholder is still in the page", () => {
    setNonceMeta("__CSP_NONCE__");
    expect(cspNonce()).toBeUndefined();
  });

  it("has none when the page has no meta tag", () => {
    setNonceMeta();
    expect(cspNonce()).toBeUndefined();
  });

  it("has none when the nonce is empty", () => {
    setNonceMeta("");
    expect(cspNonce()).toBeUndefined();
  });

  it("reads another document when given one", () => {
    const other = document.implementation.createHTMLDocument("x");
    other.head.innerHTML = '<meta name="csp-nonce" content="zzz" />';
    expect(cspNonce(other)).toBe("zzz");
  });
});
