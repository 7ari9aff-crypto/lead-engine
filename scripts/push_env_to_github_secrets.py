"""Upload provider keys from a local .env to GitHub Actions secrets.

Why: the engine reads provider keys from process env / a local .env (which is
git-ignored on purpose), so a key that only lives on a developer machine never
reaches the production worker. This copies ONLY an allow-list of provider keys
to the repository's Actions secrets, encrypted with the repo public key
(libsodium sealed box, as GitHub requires).

Safety properties (each one is unit-tested):
  * dry-run by default; nothing is sent without --apply
  * allow-list only: DB URLs, master keys, admin passwords, tokens for other
    systems in the same .env are NEVER uploaded
  * values are never printed, logged, or written anywhere; output shows names
    and a length bucket only
  * blank / placeholder values are skipped, never uploaded as empty secrets
  * existing secrets are not overwritten unless --overwrite is given

    GITHUB_TOKEN=... python scripts/push_env_to_github_secrets.py /path/.env
    GITHUB_TOKEN=... python scripts/push_env_to_github_secrets.py /path/.env --apply
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO = "7ari9aff-crypto/lead-engine"

# Keys the V6 gateway actually reads (infrastructure/providers/bootstrap.py).
# Anything not listed here is refused, whatever the .env contains.
ALLOWED = (
    "TAVILY_API_KEY", "EXA_API_KEY",            # search
    "GEMINI_API_KEY",                            # reasoning model
    "APOLLO_API_KEY", "HUNTER_API_KEY",          # contact finding / verification
)
# Documented in .env.example but NOT read by the code today: reported, not uploaded.
NOT_WIRED = ("BRAVE_SEARCH_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY", "ABSTRACT_API_KEY")

_PLACEHOLDER = re.compile(r"^(your[_-]?.*|changeme|xxx+|todo|none|null|<.*>|\.\.\.|test|example)$", re.I)


def parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.lower().startswith("export "):
            line = line[7:]
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        elif " #" in value:                       # trailing inline comment
            value = value.split(" #", 1)[0].strip()
        out[key.strip()] = value
    return out


def is_usable(value: str) -> bool:
    return bool(value) and not _PLACEHOLDER.match(value) and len(value) >= 8


def plan(env: dict[str, str], existing: set[str], overwrite: bool = False) -> dict:
    upload, skipped_blank, skipped_existing, refused = [], [], [], []
    for name in ALLOWED:
        if name not in env:
            continue
        if not is_usable(env[name]):
            skipped_blank.append(name)
        elif name in existing and not overwrite:
            skipped_existing.append(name)
        else:
            upload.append(name)
    not_wired = [n for n in NOT_WIRED if is_usable(env.get(n, ""))]
    refused = sorted(k for k in env if k not in ALLOWED and k not in NOT_WIRED
                     and is_usable(env[k]))
    return {"upload": upload, "skipped_blank": skipped_blank,
            "skipped_existing": skipped_existing, "not_wired": not_wired,
            "refused_count": len(refused)}


def seal(public_key_b64: str, value: str) -> str:
    from nacl import encoding, public
    key = public.PublicKey(public_key_b64.encode(), encoding.Base64Encoder())
    return base64.b64encode(public.SealedBox(key).encrypt(value.encode())).decode()


def _api(method: str, path: str, token: str, body: dict | None = None):
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/{path}",
        data=json.dumps(body).encode() if body is not None else None, method=method,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("env_file", type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("GITHUB_TOKEN is required"); return 2
    if not args.env_file.is_file():
        print(f"not a file: {args.env_file}"); return 2

    env = parse_env(args.env_file.read_text(encoding="utf-8"))
    existing = {s["name"] for s in _api("GET", "actions/secrets", token).get("secrets", [])}
    p = plan(env, existing, args.overwrite)

    print(f"keys in file          : {len(env)}")
    print(f"will upload           : {p['upload'] or '-'}")
    print(f"skipped (blank/dummy) : {p['skipped_blank'] or '-'}")
    print(f"skipped (exists)      : {p['skipped_existing'] or '-'}")
    print(f"present but NOT wired : {p['not_wired'] or '-'}  (code does not read these yet)")
    print(f"refused (not allowed) : {p['refused_count']} other variables, never uploaded")
    if not args.apply:
        print("\nDRY RUN: nothing sent. Re-run with --apply.")
        return 0
    if not p["upload"]:
        print("\nnothing to upload"); return 0
    pk = _api("GET", "actions/secrets/public-key", token)
    for name in p["upload"]:
        _api("PUT", f"actions/secrets/{name}", token,
             {"encrypted_value": seal(pk["key"], env[name]), "key_id": pk["key_id"]})
        print(f"  uploaded {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
