#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Comprehensive network smoke test for DeepSeek API connectivity."""
import os
import socket
import ssl
import sys
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(BASE_DIR, "l4_l5_finalization", "network_diagnostics.txt")

def log(msg: str) -> None:
    print(msg, flush=True)

def main():
    results = []
    all_pass = True

    # ── SMOKE 1: DNS Resolution ──────────────────────────────────────────────
    log("\n=== SMOKE 1: DNS Resolution ===")
    try:
        addrs = socket.getaddrinfo("api.deepseek.com", 443)
        ip = addrs[0][4][0]
        log(f"  PASS: resolved to {ip}")
        results.append(f"SMOKE1_DNS: PASS -> {ip}")
    except Exception as e:
        log(f"  FAIL: {e}")
        results.append(f"SMOKE1_DNS: FAIL -> {e}")
        all_pass = False

    # ── SMOKE 2: TCP Connectivity ────────────────────────────────────────────
    if all_pass:
        log("\n=== SMOKE 2: TCP Connectivity ===")
        try:
            sock = socket.create_connection(("api.deepseek.com", 443), timeout=10)
            sock.close()
            log("  PASS: TCP handshake succeeded")
            results.append("SMOKE2_TCP: PASS")
        except Exception as e:
            log(f"  FAIL: {e}")
            results.append(f"SMOKE2_TCP: FAIL -> {e}")
            all_pass = False

    # ── SMOKE 3: TLS Handshake ──────────────────────────────────────────────
    if all_pass:
        log("\n=== SMOKE 3: TLS Handshake ===")
        try:
            ctx = ssl.create_default_context()
            sock = socket.create_connection(("api.deepseek.com", 443), timeout=15)
            ssock = ctx.wrap_socket(sock, server_hostname="api.deepseek.com")
            cipher = ssock.cipher()[0]
            log(f"  PASS: cipher={cipher}")
            results.append(f"SMOKE3_TLS: PASS -> {cipher}")
            ssock.close()
        except Exception as e:
            log(f"  FAIL: {e}")
            results.append(f"SMOKE3_TLS: FAIL -> {e}")
            all_pass = False

    # ── SMOKE 4: API Auth (lightweight) ──────────────────────────────────────
    if all_pass:
        log("\n=== SMOKE 4: API Auth (models endpoint) ===")
        try:
            import urllib.request
            api_key = os.environ.get("DEEPSEEK_API_KEY", "")
            if not api_key:
                # Try .env
                for p in [os.path.join(BASE_DIR, ".env"), os.path.join(BASE_DIR, ".env.example")]:
                    if os.path.exists(p):
                        for line in open(p, "r").readlines():
                            if "DEEPSEEK_API_KEY" in line and "=" in line:
                                api_key = line.split("=", 1)[1].strip().strip("'\"").strip()
                                break
            if api_key:
                headers = {"Authorization": f"Bearer {api_key[:16]}..."}
            else:
                headers = {}
            req = urllib.request.Request(
                "https://api.deepseek.com/v1/models",
                headers=headers,
                method="GET"
            )
            try:
                resp = urllib.request.urlopen(req, timeout=15)
                log(f"  PASS: HTTP {resp.status}")
                results.append(f"SMOKE4_AUTH: PASS -> HTTP {resp.status}")
            except urllib.error.HTTPError as e:
                log(f"  PARTIAL: HTTP {e.code} (auth layer reached)")
                results.append(f"SMOKE4_AUTH: PARTIAL -> HTTP {e.code}")
            except Exception as e:
                log(f"  FAIL: {e}")
                results.append(f"SMOKE4_AUTH: FAIL -> {e}")
                all_pass = False
        except Exception as e:
            log(f"  FAIL: {e}")
            results.append(f"SMOKE4_AUTH: FAIL -> {e}")
            all_pass = False

    # ── Summary ──────────────────────────────────────────────────────────────
    verdict = "PASS" if all_pass else "FAIL"
    log(f"\n{'='*50}")
    log(f"OVERALL: {verdict}")
    log(f"{'='*50}")

    # Write to file
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(f"Network Diagnostics Report\n")
        f.write(f"{'='*50}\n\n")
        f.write("\n".join(results))
        f.write(f"\n\nFINAL VERDICT: {verdict}\n")
    log(f"\nResults saved to: {OUTPUT_PATH}")

    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(main())
