"""Interactive issuer for a single FPL write approval.

This module is not used by ``execute_account_mutation``. Signing requires the
private key and an explicit confirmation of the exact payload. The executor
process is expected to hold only the matching public key.
"""
from __future__ import annotations

import base64
import secrets
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, TextIO

from fpl_skill.approval_gate import ExecutionDenied
from fpl_skill.approval_verify import binding_bytes, payload_sha256


def issue_approval(
    *,
    team_id: str,
    endpoint: str,
    payload: Mapping[str, Any],
    private_key_pem: str,
    stdin: Optional[TextIO] = None,
    stdout: Optional[TextIO] = None,
    ttl_seconds: int = 600,
    now: Optional[datetime] = None,
    expires_at: Optional[str] = None,
) -> dict:
    """Show the exact change and, after confirmation, return a signed record."""
    if "PRIVATE KEY" not in private_key_pem:
        raise ExecutionDenied("approval signing key is missing")
    out = stdout if stdout is not None else sys.stdout
    rendered = json_preview(payload)
    out.write(
        "FPL write approval\n"
        f"team_id: {team_id}\n"
        f"endpoint: {endpoint}\n"
        "body:\n"
        f"{rendered}\n"
        "Type 'approve' to sign this exact change:\n"
    )
    out.flush()
    if stdin is None:
        if not sys.stdin.isatty():
            raise ExecutionDenied("interactive approval requires a TTY")
        stdin = sys.stdin
    answer = stdin.readline()
    if answer.strip() != "approve":
        raise ExecutionDenied("interactive approval was not confirmed")

    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    expiry = expires_at or (moment.astimezone(timezone.utc) + timedelta(seconds=ttl_seconds)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    nonce = secrets.token_hex(32)
    body_hash = payload_sha256(payload)
    message = binding_bytes(
        team_id=str(team_id),
        endpoint=endpoint,
        body_sha256=body_hash,
        nonce=nonce,
        expires_at=expiry,
    )
    signature = _sign(private_key_pem, message)
    return {
        "team_id": str(team_id),
        "endpoint": endpoint,
        "body_sha256": body_hash,
        "nonce": nonce,
        "expires_at": expiry,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def json_preview(payload: Mapping[str, Any]) -> str:
    import json
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True)


def _sign(private_key_pem: str, message: bytes) -> bytes:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            key_path = directory / "private.pem"
            message_path = directory / "message.bin"
            signature_path = directory / "signature.bin"
            key_path.write_text(private_key_pem, encoding="utf-8")
            message_path.write_bytes(message)
            result = subprocess.run(
                [
                    "openssl", "pkeyutl", "-sign",
                    "-inkey", str(key_path),
                    "-rawin", "-in", str(message_path),
                    "-out", str(signature_path),
                ],
                capture_output=True,
                check=False,
            )
            if result.returncode != 0 or not signature_path.exists():
                raise ExecutionDenied("approval signing failed")
            return signature_path.read_bytes()
    except OSError as exc:
        raise ExecutionDenied("approval signing failed") from exc


if __name__ == "__main__":
    import argparse
    import json
    import os

    parser = argparse.ArgumentParser(description="Sign one FPL write after an interactive confirmation.")
    parser.add_argument("--team-id", default=os.environ.get("FPL_TEAM_ID", ""))
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--payload-file", required=True)
    parser.add_argument("--signing-key", default=os.environ.get("FPL_APPROVAL_SIGNING_KEY", ""))
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if not args.team_id or not args.signing_key:
        print("FPL_TEAM_ID and a signing key path are required.", file=sys.stderr)
        sys.exit(1)
    payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    private_key = Path(args.signing_key).read_text(encoding="utf-8")
    try:
        record = issue_approval(
            team_id=args.team_id,
            endpoint=args.endpoint,
            payload=payload,
            private_key_pem=private_key,
        )
    except ExecutionDenied as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        sys.exit(1)
    Path(args.out).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.out}")
