import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";

// The UI decides "can find contacts" from the Apollo credential (store.jsx) but its
// hint told the user to connect ZoomInfo, a service the engine does not have. The hint
// must name the same service the condition checks.
const root = path.resolve(__dirname, "../..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");

describe("contact-finding hints name the provider that is actually checked", () => {
  const store = read("lib/leadEngine/store.jsx");
  const checked = /service === "(\w+)"/.exec(store.split("canFindContacts")[1] || "")?.[1];

  it("store checks Apollo", () => {
    expect(checked).toBe("Apollo");
  });

  it.each(["pages/leadEngine/ReviewQueue.jsx", "pages/leadEngine/LeadDetail.jsx"])(
    "%s never tells the user to connect ZoomInfo",
    (file) => {
      expect(read(file)).not.toMatch(/ZoomInfo/);
    },
  );

  it.each(["pages/leadEngine/ReviewQueue.jsx", "pages/leadEngine/LeadDetail.jsx"])(
    "%s points at the service the store checks",
    (file) => {
      expect(read(file)).toContain(checked);
    },
  );
});
