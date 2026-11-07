/**
 * What the conformance suite and the client must cover, read from the two lists that
 * define it. It needs no stack, so a scenario or a catalog method with nothing behind it
 * fails in every run of `npm test`.
 */

import { readFileSync } from "node:fs";
import { RoISMethods } from "@openrois/interfaces";
import { describe, expect, it } from "vitest";
import { RoISClient } from "../src/rois-client";

const README = readFileSync(
  new URL("../../../testing/conformance/README.md", import.meta.url),
  "utf8",
);
const SUITE = readFileSync(new URL("./conformance.test.ts", import.meta.url), "utf8");

/** The ids in the table under "## The List" that a client SDK has to run. */
function listedIds(): string[] {
  const [, section = ""] = README.split(/^## The List$/m);
  const [list = ""] = section.split(/^## /m);
  return [...list.matchAll(/^\| (C\d+) \|/gm)].map(([, id = ""]) => id);
}

/** The id at the start of each test name in the conformance suite. */
function testedIds(): string[] {
  return [...SUITE.matchAll(/^\s*it\("([A-Z]\d+) /gm)].map(([, id = ""]) => id);
}

describe("the conformance suite", () => {
  it("reads the list", () => {
    expect(listedIds()).toContain("C01");
  });

  it("has one test for each id of the list", () => {
    expect(testedIds()).toEqual(listedIds());
  });

  it("imports only what a client of either runtime can", () => {
    const imports = [...SUITE.matchAll(/(?:from|import) "(.+)"/g)];
    expect(imports.map(([, name]) => name)).toEqual(["vitest", "../src/rois-client"]);
  });
});

describe("the client", () => {
  it.each(Object.values(RoISMethods))("has a member for %s", (method) => {
    const name = (method.split(".").pop() ?? "").replace(/_(\w)/g, (_, letter: string) =>
      letter.toUpperCase(),
    );
    // connect is the one operation that makes a client, so it has no instance to be on.
    const owner: object = name === "connect" ? RoISClient : RoISClient.prototype;
    expect(owner).toHaveProperty(name, expect.any(Function));
  });
});
