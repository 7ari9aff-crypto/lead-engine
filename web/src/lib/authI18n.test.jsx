// The sign-in pages were English-only inside an Arabic product, used physical
// left/right classes that do not mirror, and showed raw server error text.
import React from "react";
import fs from "node:fs";
import path from "node:path";
import { renderToString } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, test, vi } from "vitest";

const store = new Map();
vi.hoisted(() => {
  const w = { location: { href: "http://localhost/", origin: "http://localhost", pathname: "/login", search: "" },
    matchMedia: () => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }),
    addEventListener() {}, removeEventListener() {} };
  w.self = w; w.top = w; globalThis.window = w;
});
vi.mock("@/lib/AuthContext", () => ({ useAuth: () => ({ signInWithPassword: async () => {} }) }));
vi.mock("@/lib/supabase", () => ({ signUp: async () => {}, resetPasswordForEmail: async () => {}, updateUserPassword: async () => {} }));

const { authDict, makeAuthT, readLang, normalizeLang, LANG_KEY } = await import("./authI18n");
const root = path.resolve(__dirname, "..");
const read = (p) => fs.readFileSync(path.join(root, p), "utf8");
const PAGES = ["pages/Login.jsx", "pages/Register.jsx", "pages/ForgotPassword.jsx", "pages/ResetPassword.jsx"];
const ARABIC = /[\u0600-\u06FF]/;

const fakeStorage = (value) => ({ getItem: (k) => (k === LANG_KEY ? value : null) });

describe("dictionary", () => {
  test.each(Object.entries(authDict))("%s has both languages, Arabic is really Arabic", (key, v) => {
    expect(v.en, key).toBeTruthy();
    expect(v.ar, key).toBeTruthy();
    if (key === "lang.switch") return;      // names the OTHER language, so scripts are swapped on purpose
    expect(v.ar, key).toMatch(ARABIC);
    expect(v.en, key).not.toMatch(ARABIC);
  });

  test("the switch button names the OTHER language", () => {
    expect(authDict["lang.switch"].ar).toBe("English");
    expect(authDict["lang.switch"].en).toBe("العربية");
  });

  test.each(PAGES)("%s only uses keys that exist", (file) => {
    const keys = [...read(file).matchAll(/\bt\("([^"]+)"\)/g)].map((m) => m[1]);
    expect(keys.length).toBeGreaterThan(2);
    for (const k of keys) expect(authDict[k], `${file} -> ${k}`).toBeDefined();
  });

  test("unknown keys fall back to the key, not undefined", () => {
    expect(makeAuthT("ar")("nope.nope")).toBe("nope.nope");
  });
});

describe("language selection shares the app's persisted key", () => {
  test("defaults to Arabic, like the app", () => {
    expect(readLang(fakeStorage(null))).toBe("ar");
    expect(readLang(fakeStorage("garbage"))).toBe("ar");
  });
  test("honours a saved English choice", () => expect(readLang(fakeStorage("en"))).toBe("en"));
  test("unavailable storage does not crash", () => {
    expect(readLang({ getItem() { throw new Error("denied"); } })).toBe("ar");
  });
  test("uses the same key as the signed-in app", () => {
    expect(LANG_KEY).toBe("leadengine.lang");
    expect(read("lib/leadEngine/store.jsx")).toContain(`"${LANG_KEY}"`);
    expect(normalizeLang("en")).toBe("en");
  });
});

describe("layout mirrors", () => {
  test.each([...PAGES, "components/AuthLayout.jsx"])("%s has no physical left/right utilities", (file) => {
    expect(read(file)).not.toMatch(/\b(?:left|right)-\d|\b(?:pl|pr|ml|mr)-\d/);
  });
  test("the icon sits at the start edge and text is padded from it", () => {
    expect(read("pages/Login.jsx")).toContain("absolute start-3");
    expect(read("pages/Login.jsx")).toContain("ps-10");
  });
  test("the orphan 'or' divider (no button above it) is gone", () => {
    expect(read("pages/Login.jsx")).not.toMatch(/>\s*or\s*</);
  });
  test.each(PAGES)("%s no longer shows raw server error text", (file) => {
    expect(read(file)).not.toMatch(/err\.message/);
  });
});

describe("rendered pages", () => {
  const render = async (file, route = "/", extra = {}) => {
    const mod = await import(/* @vite-ignore */ path.join(root, file));
    return renderToString(<MemoryRouter initialEntries={[route]}><mod.default {...extra} /></MemoryRouter>);
  };

  test.each([["pages/Login.jsx"], ["pages/Register.jsx"], ["pages/ForgotPassword.jsx"], ["pages/ResetPassword.jsx", "/reset?token=abc"],
    ["pages/ResetPassword.jsx", "/reset"]])("%s renders RTL Arabic by default with no English leftovers", async (file, route) => {
    const html = await render(file, route);
    expect(html).toContain('dir="rtl"');
    expect(html).toContain('lang="ar"');
    expect(html).toMatch(ARABIC);
    for (const english of ["Welcome back", "Log in", "Password", "Create", "Sign up", "Reset password", "Invalid", "Email"]) {
      expect(html, `${file} leaks "${english}"`).not.toContain(english);
    }
    expect(html).toContain("English");              // the switch offers the other language
  });

  test("email and password inputs stay LTR (Latin content) but align to the start", async () => {
    const html = await render("pages/Login.jsx");
    expect((html.match(/dir="ltr"/g) || []).length).toBe(2);
    expect(html).toContain("ps-10");
  });
});
