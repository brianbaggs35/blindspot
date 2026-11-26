import { flushPromises } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import EvidenceDialog from "../src/views/findings/EvidenceDialog.vue";
import EvidenceList from "../src/views/findings/EvidenceList.vue";
import CvssCalculator from "../src/views/findings/CvssCalculator.vue";
import FindingFormDialog from "../src/views/findings/FindingFormDialog.vue";
import ImportFindingsDialog from "../src/views/findings/ImportFindingsDialog.vue";
import MergeDialog from "../src/views/findings/MergeDialog.vue";
import { alertText, emitFrom, fieldNamed } from "./pentest-fixtures";
import { dialogButton, mockApi, mountWithApp, submitDialog } from "./helpers";
import { evidenceOf, findingOf } from "./findings-fixtures";

afterEach(() => {
  vi.restoreAllMocks();
});

const BASE = "/api/pentests/p-1/findings";
const V4 = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:N/VA:N/SC:N/SI:N/SA:N";
const REFERENCE = { owasp: { A05: "Security Misconfiguration" }, transitions: {} };
const SCORE = `GET /api/cvss/score?vector=${encodeURIComponent(V4)}`;

/** Mounts a dialog closed and then opens it, as a page does. */
async function opened(component: Parameters<typeof mountWithApp>[0], props: object) {
  const mounted = await mountWithApp(component, "/", { modelValue: false, ...props });
  await mounted.wrapper.setProps({ modelValue: true });
  await flushPromises();
  return mounted;
}

describe("CvssCalculator", () => {
  async function calculator(version: "3.1" | "4.0", start: string | null, handlers = {}) {
    const api = mockApi(handlers);
    const { wrapper } = await mountWithApp(CvssCalculator, "/", { version, modelValue: start });
    await wrapper.setProps({
      "onUpdate:modelValue": (value: string | null) => wrapper.setProps({ modelValue: value }),
    });
    await flushPromises();
    return { wrapper, ...api };
  }

  it("shows the score the server works out for a vector", async () => {
    const { wrapper, calls } = await calculator("4.0", V4, {
      [SCORE]: { json: { vector: V4, version: "4.0", score: "8.7", severity: "high" } },
    });
    expect(wrapper.text()).toContain("8.7 · High");
    expect(calls.map((one) => one.key)).toEqual([SCORE]);
    expect(fieldNamed(wrapper, "VTextField", "CVSS 4.0 vector").props("modelValue")).toBe(V4);
  });

  it("builds the vector from the metrics once all are chosen", async () => {
    const { wrapper } = await calculator("3.1", null, {});
    expect(wrapper.text()).not.toContain("·");
    const values: Record<string, string> = {
      AV: "N",
      AC: "L",
      PR: "N",
      UI: "N",
      S: "U",
      C: "H",
      I: "H",
      A: "H",
    };
    const vectorOf = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H";
    const api = mockApi({
      [`GET /api/cvss/score?vector=${encodeURIComponent(vectorOf)}`]: {
        json: { vector: vectorOf, version: "3.1", score: "9.8", severity: "critical" },
      },
    });
    for (const [key, value] of Object.entries(values)) {
      const select = wrapper
        .findAllComponents({ name: "VSelect" })
        .find((one) => String(one.props("label")).endsWith(`(${key})`));
      if (select === undefined) throw new Error(`no ${key}`);
      emitFrom(select, "update:modelValue", value);
      await flushPromises();
    }
    expect(wrapper.text()).toContain("9.8 · Critical");
    expect(api.calls).toHaveLength(1);
    // Taking a metric away empties the vector again.
    const first = wrapper
      .findAllComponents({ name: "VSelect" })
      .find((one) => String(one.props("label")).endsWith("(AV)"));
    emitFrom(first ?? wrapper, "update:modelValue", null);
    await flushPromises();
    expect(wrapper.text()).not.toContain("9.8");
  });

  it("takes a vector that is typed or pasted, and clears it", async () => {
    const { wrapper } = await calculator("4.0", null, {
      [SCORE]: { json: { vector: V4, version: "4.0", score: "8.7", severity: "high" } },
    });
    const field = fieldNamed(wrapper, "VTextField", "CVSS 4.0 vector");
    await field.setValue(` ${V4} `);
    await field.find("input").trigger("blur");
    await flushPromises();
    expect(wrapper.text()).toContain("8.7 · High");
    await field.setValue("");
    await field.find("input").trigger("keydown.enter");
    await flushPromises();
    expect(wrapper.text()).not.toContain("8.7");
  });

  it("says what is wrong with a vector the server does not accept", async () => {
    const { wrapper } = await calculator("4.0", "CVSS:4.0/AV:N", {
      [`GET /api/cvss/score?vector=${encodeURIComponent("CVSS:4.0/AV:N")}`]: {
        status: 422,
        json: { code: "bad_vector", title: "That vector is not complete" },
      },
    });
    expect(wrapper.text()).toContain("That vector is not complete");
  });

  it("ignores a score that arrives after a newer vector, and a late failure", async () => {
    let release: () => void = () => undefined;
    const slow = new Promise<void>((done) => {
      release = done;
    });
    const { wrapper, fetchMock } = await calculator("4.0", null);
    fetchMock.mockImplementationOnce(async () => {
      await slow;
      return new Response(
        JSON.stringify({ vector: "a", version: "4.0", score: "1.0", severity: "low" }),
      );
    });
    fetchMock.mockImplementationOnce(async () => {
      await slow;
      return new Response(JSON.stringify({ title: "late" }), { status: 422 });
    });
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({ vector: V4, version: "4.0", score: "8.7", severity: "high" }),
        ),
      ),
    );
    emitFrom(wrapper.getComponent({ name: "VTextField" }), "update:modelValue", "first");
    await wrapper.setProps({ modelValue: "CVSS:4.0/AV:L" });
    await wrapper.setProps({ modelValue: "CVSS:4.0/AV:A" });
    await wrapper.setProps({ modelValue: V4 });
    await flushPromises();
    release();
    await flushPromises();
    expect(wrapper.text()).toContain("8.7 · High");
    expect(wrapper.text()).not.toContain("1.0");
  });
});

describe("FindingFormDialog", () => {
  it("writes a finding with its lists split into words", async () => {
    const api = mockApi({
      "GET /api/findings/reference": { json: REFERENCE },
      [`POST ${BASE}`]: { status: 201, json: findingOf() },
      [SCORE]: { json: { vector: V4, version: "4.0", score: "8.7", severity: "high" } },
    });
    const { wrapper } = await opened(FindingFormDialog, { pentestId: "p-1" });
    expect(document.body.textContent).toContain("Write a finding");
    expect(
      document.body.querySelector<HTMLButtonElement>(".v-dialog button[type=submit]")?.disabled,
    ).toBe(true);
    await fieldNamed(wrapper, "VTextField", "Title").setValue("Open redirect");
    await fieldNamed(wrapper, "VTextarea", "What is wrong").setValue("It redirects");
    await fieldNamed(wrapper, "VTextField", "Affected target (a URL, host or path)").setValue(
      "/go",
    );
    await fieldNamed(wrapper, "VSelect", "OWASP Top 10").setValue("A05");
    await fieldNamed(wrapper, "VSelect", "Confidence").setValue("certain");
    await fieldNamed(wrapper, "VTextarea", "How to fix it").setValue("Check the target");
    await fieldNamed(wrapper, "VTextField", "Tests (WSTG-CONF-07 …)").setValue(
      "WSTG-CLNT-04, WSTG-CLNT-04",
    );
    await fieldNamed(wrapper, "VTextField", "CWE (CWE-79 …)").setValue("cwe-601 cwe-79");
    await fieldNamed(wrapper, "VTextarea", "References (one web address on each line)").setValue(
      "https://a.example\n\n  https://b.example  ",
    );
    emitFrom(fieldNamed(wrapper, "VSelect", "Severity"), "update:modelValue", "medium");
    await flushPromises();
    await submitDialog();
    expect(api.calls.find((one) => one.key === `POST ${BASE}`)?.body).toMatchObject({
      title: "Open redirect",
      description: "It redirects",
      target: "/go",
      owasp: "A05",
      confidence: "certain",
      remediation: "Check the target",
      severity: "medium",
      test_ids: ["WSTG-CLNT-04"],
      cwe: ["CWE-601", "CWE-79"],
      references: ["https://a.example", "https://b.example"],
    });
    expect(wrapper.emitted("saved")).toHaveLength(1);
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("closes without saving when asked to cancel", async () => {
    mockApi({ "GET /api/findings/reference": { json: REFERENCE } });
    const { wrapper } = await opened(FindingFormDialog, { pentestId: "p-1" });
    dialogButton("Cancel")?.click();
    await flushPromises();
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("can be rated with a vector alone, from either version", async () => {
    mockApi({
      "GET /api/findings/reference": { json: REFERENCE },
      [SCORE]: { json: { vector: V4, version: "4.0", score: "8.7", severity: "high" } },
    });
    const { wrapper } = await opened(FindingFormDialog, { pentestId: "p-1" });
    await fieldNamed(wrapper, "VTextField", "Title").setValue("Open redirect");
    const submit = () =>
      document.body.querySelector<HTMLButtonElement>(".v-dialog button[type=submit]");
    expect(submit()?.disabled).toBe(true);
    emitFrom(wrapper.getComponent(CvssCalculator), "update:modelValue", V4);
    await flushPromises();
    expect(submit()?.disabled).toBe(false);
    emitFrom(wrapper.getComponent({ name: "VTabs" }), "update:modelValue", "3.1");
    await flushPromises();
    expect(wrapper.getComponent(CvssCalculator).props("version")).toBe("3.1");
    emitFrom(wrapper.getComponent(CvssCalculator), "update:modelValue", "CVSS:3.1/AV:N");
    await flushPromises();
  });

  it("changes a finding, leaving out a severity that was not touched", async () => {
    const api = mockApi({
      "GET /api/findings/reference": { json: REFERENCE },
      [`PATCH ${BASE}/f-1`]: { json: findingOf() },
      [SCORE]: { json: { vector: V4, version: "4.0", score: "8.7", severity: "high" } },
    });
    const { wrapper } = await opened(FindingFormDialog, {
      pentestId: "p-1",
      finding: findingOf(),
    });
    expect(document.body.textContent).toContain("Change the finding");
    expect(fieldNamed(wrapper, "VTextField", "Title").props("modelValue")).toBe(
      "Missing HSTS header",
    );
    await submitDialog();
    const body = api.calls.find((one) => one.key === `PATCH ${BASE}/f-1`)?.body;
    expect(body).not.toHaveProperty("severity");
    expect(body).toMatchObject({ title: "Missing HSTS header", test_ids: ["WSTG-CONF-07"] });

    emitFrom(fieldNamed(wrapper, "VSelect", "Severity"), "update:modelValue", "low");
    await submitDialog();
    expect(api.calls.filter((one) => one.key === `PATCH ${BASE}/f-1`).at(-1)?.body).toMatchObject({
      severity: "low",
    });
  });

  it("says why saving failed and keeps the form", async () => {
    mockApi({
      "GET /api/findings/reference": { json: REFERENCE },
      [`PATCH ${BASE}/f-1`]: { status: 422, json: { code: "bad_vector", title: "Bad vector" } },
      [SCORE]: { json: { vector: V4, version: "4.0", score: "8.7", severity: "high" } },
    });
    const { wrapper } = await opened(FindingFormDialog, { pentestId: "p-1", finding: findingOf() });
    await submitDialog();
    expect(alertText()).toContain("Bad vector");
    expect(wrapper.emitted("saved")).toBeUndefined();
  });

  it("says when the OWASP list could not be loaded, and asks for it only once", async () => {
    const api = mockApi({
      "GET /api/findings/reference": { status: 500, json: { code: "x", title: "No list" } },
    });
    const { wrapper } = await opened(FindingFormDialog, { pentestId: "p-1" });
    expect(alertText()).toContain("No list");
    api.fetchMock.mockClear();
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(api.calls.filter((one) => one.key === "GET /api/findings/reference")).toHaveLength(2);
  });

  it("asks for the OWASP list once it has it", async () => {
    const api = mockApi({ "GET /api/findings/reference": { json: REFERENCE } });
    const { wrapper } = await opened(FindingFormDialog, { pentestId: "p-1" });
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(api.calls.filter((one) => one.key === "GET /api/findings/reference")).toHaveLength(1);
  });
});

describe("MergeDialog", () => {
  const LIST = `GET ${BASE}?limit=200&sort=number&order=asc`;

  it("starts with the finding that looks like this one", async () => {
    const api = mockApi({
      [LIST]: {
        json: {
          items: [
            { id: "f-1", number: 1, title: "Mine" },
            { id: "f-2", number: 2, title: "Other" },
          ],
        },
      },
      [`POST ${BASE}/f-1/merge`]: { json: findingOf({ id: "f-2" }) },
    });
    const { wrapper } = await opened(MergeDialog, {
      pentestId: "p-1",
      finding: findingOf({
        duplicates: [{ id: "f-2", number: 2, title: "Other", status: "new", reason: "same" }],
      }),
    });
    expect(fieldNamed(wrapper, "VSelect", "Keep this finding").props("modelValue")).toBe("f-2");
    await submitDialog();
    expect(api.calls.find((one) => one.key === `POST ${BASE}/f-1/merge`)?.body).toEqual({
      into: "f-2",
    });
    expect(wrapper.emitted("merged")).toHaveLength(1);
  });

  it("closes when asked to cancel", async () => {
    mockApi({ [LIST]: { json: { items: [] } } });
    const { wrapper } = await opened(MergeDialog, { pentestId: "p-1", finding: findingOf() });
    dialogButton("Cancel")?.click();
    await flushPromises();
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("says why the list or the merge failed", async () => {
    let fail = true;
    mockApi({
      [LIST]: () =>
        fail
          ? { status: 500, json: { code: "x", title: "No list" } }
          : { json: { items: [{ id: "f-2", number: 2, title: "Other" }] } },
      [`POST ${BASE}/f-1/merge`]: { status: 409, json: { code: "x", title: "Cannot merge" } },
    });
    const { wrapper } = await opened(MergeDialog, { pentestId: "p-1", finding: findingOf() });
    expect(alertText()).toContain("No list");
    fail = false;
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    emitFrom(fieldNamed(wrapper, "VSelect", "Keep this finding"), "update:modelValue", "f-2");
    await submitDialog();
    expect(alertText()).toContain("Cannot merge");
  });
});

describe("ImportFindingsDialog", () => {
  const IMPORT = `POST ${BASE}/import`;

  it("sends the text of a file that was loaded, as SARIF when it is one", async () => {
    const api = mockApi({ [IMPORT]: { json: { created: 1, skipped: 0 } } });
    const { wrapper } = await opened(ImportFindingsDialog, { pentestId: "p-1" });
    const file = new File(['{"runs":[]}'], "report.sarif", { type: "application/json" });
    emitFrom(wrapper.getComponent({ name: "VFileInput" }), "update:modelValue", file);
    await flushPromises();
    await submitDialog();
    expect(api.calls.find((one) => one.key === IMPORT)?.body).toEqual({
      format: "sarif",
      content: '{"runs":[]}',
    });
    expect(wrapper.emitted("imported")).toEqual([["1 imported."]]);
  });

  it("closes when asked to cancel", async () => {
    mockApi({});
    const { wrapper } = await opened(ImportFindingsDialog, { pentestId: "p-1" });
    dialogButton("Cancel")?.click();
    await flushPromises();
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("takes a list of files, a file that is not SARIF, and no file at all", async () => {
    const api = mockApi({ [IMPORT]: { json: { created: 0, skipped: 2 } } });
    const { wrapper } = await opened(ImportFindingsDialog, { pentestId: "p-1" });
    const input = wrapper.getComponent({ name: "VFileInput" });
    emitFrom(input, "update:modelValue", null);
    await flushPromises();
    expect(
      document.body.querySelector<HTMLButtonElement>(".v-dialog button[type=submit]")?.disabled,
    ).toBe(true);
    emitFrom(input, "update:modelValue", [new File(["[]"], "findings.json")]);
    await flushPromises();
    await submitDialog();
    expect(api.calls.find((one) => one.key === IMPORT)?.body).toEqual({
      format: "json",
      content: "[]",
    });
    expect(wrapper.emitted("imported")).toEqual([["0 imported, 2 skipped."]]);
  });

  it("says why it failed and starts empty each time it opens", async () => {
    mockApi({ [IMPORT]: { status: 422, json: { code: "x", title: "Not a report" } } });
    const { wrapper } = await opened(ImportFindingsDialog, { pentestId: "p-1" });
    await fieldNamed(wrapper, "VSelect", "What the file is").setValue("sarif");
    await fieldNamed(wrapper, "VTextarea", "Contents").setValue("nope");
    await submitDialog();
    expect(alertText()).toContain("Not a report");
    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();
    expect(fieldNamed(wrapper, "VTextarea", "Contents").props("modelValue")).toBe("");
    expect(alertText()).toBe("");
  });
});

describe("EvidenceDialog", () => {
  const ADD = `POST ${BASE}/f-1/evidence`;
  const RESULTS = "GET /api/pentests/p-1/results?limit=200";
  const results = { items: [{ id: "r-1", title: "Nmap scan" }] };

  it("closes when asked to cancel", async () => {
    mockApi({ [RESULTS]: { json: results } });
    const { wrapper } = await opened(EvidenceDialog, { pentestId: "p-1", findingId: "f-1" });
    dialogButton("Cancel")?.click();
    await flushPromises();
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([false]);
  });

  it("adds a note, sealed when asked", async () => {
    const api = mockApi({ [RESULTS]: { json: results }, [ADD]: { status: 201, json: {} } });
    const { wrapper } = await opened(EvidenceDialog, { pentestId: "p-1", findingId: "f-1" });
    const submit = () =>
      document.body.querySelector<HTMLButtonElement>(".v-dialog button[type=submit]");
    expect(submit()?.disabled).toBe(true);
    await fieldNamed(wrapper, "VTextField", "Title").setValue("  How I saw it ");
    await fieldNamed(wrapper, "VTextarea", "Note").setValue("curl -I");
    emitFrom(wrapper.getComponent({ name: "VCheckbox" }), "update:modelValue", true);
    await flushPromises();
    await submitDialog();
    expect(api.calls.find((one) => one.key === ADD)?.body).toEqual({
      kind: "note",
      title: "How I saw it",
      sealed: true,
      body: "curl -I",
    });
    expect(wrapper.emitted("added")).toHaveLength(1);
  });

  it("lets the server decide on sealing until the box is ticked, and unticked", async () => {
    const api = mockApi({ [RESULTS]: { json: results }, [ADD]: { status: 201, json: {} } });
    const { wrapper } = await opened(EvidenceDialog, { pentestId: "p-1", findingId: "f-1" });
    await fieldNamed(wrapper, "VSelect", "What it is").setValue("request_response");
    await fieldNamed(wrapper, "VTextField", "Title").setValue("Exchange");
    await fieldNamed(wrapper, "VTextarea", "The request and the response").setValue("GET /");
    const box = wrapper.getComponent({ name: "VCheckbox" });
    emitFrom(box, "update:modelValue", true);
    emitFrom(box, "update:modelValue", false);
    await flushPromises();
    await submitDialog();
    expect(api.calls.find((one) => one.key === ADD)?.body).toMatchObject({
      kind: "request_response",
      sealed: null,
    });
  });

  it("links a result of the pentest", async () => {
    const api = mockApi({ [RESULTS]: { json: results }, [ADD]: { status: 201, json: {} } });
    const { wrapper } = await opened(EvidenceDialog, { pentestId: "p-1", findingId: "f-1" });
    await fieldNamed(wrapper, "VSelect", "What it is").setValue("result");
    await fieldNamed(wrapper, "VTextField", "Title").setValue("The scan");
    emitFrom(fieldNamed(wrapper, "VSelect", "Which result"), "update:modelValue", "r-1");
    await flushPromises();
    expect(wrapper.findAllComponents({ name: "VCheckbox" })).toHaveLength(0);
    await submitDialog();
    expect(api.calls.find((one) => one.key === ADD)?.body).toEqual({
      kind: "result",
      title: "The scan",
      sealed: null,
      result_id: "r-1",
    });
  });

  it("reads a screenshot as base64 and names it after the file", async () => {
    const api = mockApi({ [RESULTS]: { json: results }, [ADD]: { status: 201, json: {} } });
    const { wrapper } = await opened(EvidenceDialog, { pentestId: "p-1", findingId: "f-1" });
    await fieldNamed(wrapper, "VSelect", "What it is").setValue("screenshot");
    const input = wrapper.getComponent({ name: "VFileInput" });
    emitFrom(input, "update:modelValue", [
      new File([new Uint8Array([137, 80, 78, 71])], "shot.png", { type: "image/png" }),
    ]);
    await vi.waitFor(() => {
      expect(fieldNamed(wrapper, "VTextField", "Title").props("modelValue")).toBe("shot.png");
    });
    await flushPromises();
    await submitDialog();
    expect(api.calls.find((one) => one.key === ADD)?.body).toMatchObject({
      kind: "screenshot",
      title: "shot.png",
      body: "iVBORw==",
      mime: "image/png",
    });
  });

  it("keeps the title that was typed, takes a single file, and clears the picture", async () => {
    mockApi({ [RESULTS]: { json: results } });
    const { wrapper } = await opened(EvidenceDialog, { pentestId: "p-1", findingId: "f-1" });
    await fieldNamed(wrapper, "VSelect", "What it is").setValue("screenshot");
    await fieldNamed(wrapper, "VTextField", "Title").setValue("Mine");
    const input = wrapper.getComponent({ name: "VFileInput" });
    emitFrom(
      input,
      "update:modelValue",
      new File([new Uint8Array([1])], "one.png", { type: "image/png" }),
    );
    await vi.waitFor(() => {
      expect(fieldNamed(wrapper, "VTextField", "Title").props("modelValue")).toBe("Mine");
    });
    await flushPromises();
    expect(fieldNamed(wrapper, "VTextField", "Title").props("modelValue")).toBe("Mine");
    emitFrom(input, "update:modelValue", null);
    await flushPromises();
    expect(
      document.body.querySelector<HTMLButtonElement>(".v-dialog button[type=submit]")?.disabled,
    ).toBe(true);
  });

  it("refuses a screenshot over 2 MB", async () => {
    mockApi({ [RESULTS]: { json: results } });
    const { wrapper } = await opened(EvidenceDialog, { pentestId: "p-1", findingId: "f-1" });
    await fieldNamed(wrapper, "VSelect", "What it is").setValue("screenshot");
    const big = new File([new Uint8Array(2 * 1024 * 1024 + 1)], "big.png", { type: "image/png" });
    emitFrom(wrapper.getComponent({ name: "VFileInput" }), "update:modelValue", big);
    await flushPromises();
    expect(alertText()).toContain("A screenshot may be 2 MB at most.");
  });

  it("says why adding failed, and why the results could not be listed", async () => {
    mockApi({
      [RESULTS]: { status: 500, json: { code: "x", title: "No results" } },
      [ADD]: { status: 422, json: { code: "x", title: "Too big" } },
    });
    const { wrapper } = await opened(EvidenceDialog, { pentestId: "p-1", findingId: "f-1" });
    expect(alertText()).toContain("No results");
    await fieldNamed(wrapper, "VTextField", "Title").setValue("A");
    await fieldNamed(wrapper, "VTextarea", "Note").setValue("b");
    await submitDialog();
    expect(alertText()).toContain("Too big");
  });
});

describe("EvidenceList", () => {
  const EV = `${BASE}/f-1/evidence`;

  async function list(evidence = [evidenceOf()], props: object = {}) {
    const api = mockApi({});
    const { wrapper } = await mountWithApp(EvidenceList, "/", {
      pentestId: "p-1",
      findingId: "f-1",
      evidence,
      canEdit: true,
      canReveal: true,
      ...props,
    });
    return { wrapper, ...api };
  }

  it("says there is none yet", async () => {
    const { wrapper } = await list([]);
    expect(wrapper.text()).toContain("No evidence yet.");
  });

  it("shows a note, a request, a result link and a picture each their own way", async () => {
    const { wrapper } = await list([
      evidenceOf(),
      evidenceOf({
        id: "e-2",
        kind: "result",
        title: "Step 1",
        result_id: "r-1",
        result_title: "Nmap scan",
        body: null,
      }),
      evidenceOf({
        id: "e-3",
        kind: "result",
        title: "Step 2",
        result_id: "r-2",
        result_title: null,
        body: null,
      }),
      evidenceOf({ id: "e-4", kind: "screenshot", title: "Shot", mime: "image/png", body: null }),
      evidenceOf({
        id: "e-5",
        kind: "screenshot",
        title: "Hidden",
        mime: "image/png",
        sealed: true,
        body: null,
      }),
    ]);
    const text = wrapper.text();
    expect(text).toContain("curl -I shows no Strict-Transport-Security");
    expect(wrapper.find("a[href='/pentests/p-1/results/r-1']").text()).toBe("Nmap scan");
    expect(wrapper.find("a[href='/pentests/p-1/results/r-2']").text()).toBe("The result");
    expect(wrapper.find("img[alt=Shot]").attributes("src")).toBe(`${EV}/e-4/image`);
    expect(text).toContain("The screenshot is sealed.");
  });

  it("shows nothing but a mask for sealed text until it is revealed, then seals it again", async () => {
    const { wrapper, calls } = await list([evidenceOf({ sealed: true, body: "••••" })]);
    expect(wrapper.text()).toContain("••••");
    const handlers = mockApi({
      [`POST ${EV}/e-1/reveal`]: { json: { body: "Authorization: Bearer abc" } },
      [`PATCH ${EV}/e-1`]: { json: {} },
    });
    await wrapper
      .findAll("button")
      .find((one) => one.text() === "Reveal")
      ?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Authorization: Bearer abc");
    expect(wrapper.text()).not.toContain("Reveal");
    await wrapper.get("button[aria-label='Unseal How I saw it']").trigger("click");
    await flushPromises();
    expect(handlers.calls.map((one) => one.key)).toContain(`PATCH ${EV}/e-1`);
    expect(wrapper.text()).not.toContain("Authorization: Bearer abc");
    expect(wrapper.emitted("changed")).toEqual([["Unsealed."]]);
    expect(calls).toEqual([]);
  });

  it("shows a sealed picture after it is revealed", async () => {
    const { wrapper } = await list([
      evidenceOf({ kind: "screenshot", sealed: true, mime: "image/png", body: null }),
    ]);
    mockApi({ [`POST ${EV}/e-1/reveal`]: { json: { body: "iVBORw==" } } });
    await wrapper
      .findAll("button")
      .find((one) => one.text() === "Reveal")
      ?.trigger("click");
    await flushPromises();
    expect(wrapper.find("img").attributes("src")).toBe("data:image/png;base64,iVBORw==");
  });

  it("shows a revealed picture even when its type was not kept", async () => {
    const { wrapper } = await list([
      evidenceOf({ kind: "screenshot", sealed: true, mime: null, body: null }),
    ]);
    mockApi({ [`POST ${EV}/e-1/reveal`]: { json: { body: "AA==" } } });
    await wrapper
      .findAll("button")
      .find((one) => one.text() === "Reveal")
      ?.trigger("click");
    await flushPromises();
    expect(wrapper.find("img").attributes("src")).toBe("data:;base64,AA==");
  });

  it("seals what is not sealed and removes evidence", async () => {
    const { wrapper } = await list();
    const api = mockApi({
      [`PATCH ${EV}/e-1`]: { json: {} },
      [`DELETE ${EV}/e-1`]: { status: 204 },
    });
    await wrapper.get("button[aria-label='Seal How I saw it']").trigger("click");
    await flushPromises();
    await wrapper.get("button[aria-label='Remove How I saw it']").trigger("click");
    await flushPromises();
    expect(api.calls).toEqual([
      { key: `PATCH ${EV}/e-1`, body: { sealed: true } },
      { key: `DELETE ${EV}/e-1`, body: undefined },
    ]);
    expect(wrapper.emitted("changed")).toEqual([["Sealed."], ["Evidence removed."]]);
  });

  it("does not offer to seal a result link, and shows no controls to a viewer", async () => {
    const { wrapper } = await list(
      [evidenceOf({ kind: "result", title: "Step 1", result_id: "r-1", body: null })],
      {},
    );
    expect(wrapper.find("button[aria-label='Seal Step 1']").exists()).toBe(false);
    expect(wrapper.find("button[aria-label='Remove Step 1']").exists()).toBe(true);
    const viewer = await list([evidenceOf({ sealed: true, body: "••••" })], {
      canEdit: false,
      canReveal: false,
    });
    expect(viewer.wrapper.findAll("button")).toHaveLength(0);
  });

  it("says why an action failed", async () => {
    const { wrapper } = await list([evidenceOf({ sealed: true, body: "••••" })]);
    mockApi({
      [`POST ${EV}/e-1/reveal`]: { status: 404, json: { code: "x", title: "Nothing to reveal" } },
      [`PATCH ${EV}/e-1`]: { status: 409, json: { code: "x", title: "Cannot seal" } },
      [`DELETE ${EV}/e-1`]: { status: 409, json: { code: "x", title: "Cannot remove" } },
    });
    await wrapper
      .findAll("button")
      .find((one) => one.text() === "Reveal")
      ?.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Nothing to reveal");
    await wrapper.get("button[aria-label='Unseal How I saw it']").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Cannot seal");
    await wrapper.get("button[aria-label='Remove How I saw it']").trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Cannot remove");
  });
});
