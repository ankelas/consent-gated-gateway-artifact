"""Stage 0 preflight for the live study: read-only, no tasks, no side effects.

Records the identity of every agent under test, verifies the mTLS paths with
the existing client material, and writes a run manifest. It refuses to print or
store phone numbers, tokens, or key material.

Usage:

    python3 experiments/live/preflight.py --out experiments/data/live_preflight.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import ssl
import subprocess
from pathlib import Path


CLIENT_DIR = Path("/data/caiyizhang/acps-upgrade-20260924/mq-e2e-20260928/keyfiles")
TLS_ENDPOINTS = (
    ("prereg-gateway-a", "127.0.0.1", 9520),
    ("prereg-gateway-b", "127.0.0.1", 9521),
)
AGENTS = (
    ("assistant-a", ("ASSISTANT_AIC", "ASSISTANT_TLS_PORT")),
    ("assistant-b", ("ASSISTANT_AIC", "ASSISTANT_TLS_PORT")),
    ("caiyizhang-acps-leader", ("LEADER_LLM_DEFAULT_MODEL",)),
    ("caiyizhang-acps-partner", ("PARTNER_LLM_DEFAULT_MODEL",)),
    ("imessage-sender", (
        "FORWARDER_AGENT_AIC",
        "FORWARDER_IDENTITY_BINDING_ENABLED",
        "AIP_SERVER_IDENTITY_BINDING_ENABLED",
        "SENDER_DRY_RUN",
    )),
)


def sh(*args: str) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def container_env(name: str) -> dict[str, str]:
    raw = sh("docker", "inspect", name, "--format", "{{range .Config.Env}}{{println .}}{{end}}")
    out: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key] = value
    return out


def inventory() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name, keys in AGENTS:
        env = container_env(name)
        rows.append({
            "container": name,
            "image_id": sh("docker", "inspect", name, "--format", "{{.Image}}")[:19],
            "running": sh("docker", "inspect", name, "--format", "{{.State.Status}}"),
            "fields": {key: env.get(key, "") for key in keys},
        })
    return rows


def mtls() -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for label, host, port in TLS_ENDPOINTS:
        entry: dict[str, object] = {"label": label, "host": host, "port": port, "ok": False}
        try:
            ctx = ssl.create_default_context(cafile=str(CLIENT_DIR / "trust-bundle.pem"))
            ctx.load_cert_chain(str(CLIENT_DIR / "client.pem"), str(CLIENT_DIR / "client.key"))
            ctx.check_hostname = False
            with socket.create_connection((host, port), timeout=6) as raw:
                with ctx.wrap_socket(raw, server_hostname=host) as tls:
                    cert = tls.getpeercert()
                    cns = [v for rdn in cert.get("subject", ()) for k, v in rdn if k == "commonName"]
                    entry.update({"ok": True, "peer_cn": cns, "protocol": tls.version()})
        except Exception as error:  # noqa: BLE001 - recorded, not raised
            entry["error"] = f"{type(error).__name__}: {error}"[:120]
        results.append(entry)
    return results


def client_identity() -> dict[str, object]:
    pem = CLIENT_DIR / "client.pem"
    return {
        "subject": sh("openssl", "x509", "-in", str(pem), "-noout", "-subject"),
        "not_after": sh("openssl", "x509", "-in", str(pem), "-noout", "-enddate"),
        "sha256": sh("openssl", "x509", "-in", str(pem), "-noout", "-fingerprint", "-sha256"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("experiments/data/live_preflight.json"))
    args = parser.parse_args()

    manifest = {
        "stage": "0-preflight",
        "recorded_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "read_only": True,
        "agents": inventory(),
        "mtls": mtls(),
        "client_identity": client_identity(),
        "gates": {
            "G1_identity_binding_target_set": False,
            "G2_allowlist_confirmed_and_dry_run": False,
            "G3_message_suite_frozen_and_annotators": False,
            "G4_telemetry_sink": True,
            "G5_kill_switch": False,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    ok = all(entry["ok"] for entry in manifest["mtls"])
    sender = next(a for a in manifest["agents"] if a["container"] == "imessage-sender")
    dry_run = sender["fields"].get("SENDER_DRY_RUN", "")
    print(f"preflight written to {args.out}")
    print(f"  mTLS endpoints reachable : {ok}")
    print(f"  sender dry-run flag      : {dry_run or '(unset -> armed for real sends)'}")
    print(f"  agents inventoried       : {len(manifest['agents'])}")
    print("  stage 1 may not start until G2 is signed off" if not dry_run else "  dry-run is armed; stage 1 may start")


if __name__ == "__main__":
    main()
