"""Verify an out-of-band FPL write approval.

The execution path holds a public key only. It cannot produce a signature.
Approvals are bound to the team id, endpoint, canonical body, nonce, and
expiry, and each nonce can be consumed once.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from fpl_skill.approval_gate import ExecutionDenied


def payload_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def binding_bytes(
    *,
    team_id: str,
    endpoint: str,
    body_sha256: str,
    nonce: str,
    expires_at: str,
) -> bytes:
    body = {
        "body_sha256": body_sha256,
        "endpoint": endpoint,
        "expires_at": expires_at,
        "nonce": nonce,
        "team_id": str(team_id),
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def parse_expiry(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def verify_signature(public_key_pem: str, message: bytes, signature: bytes) -> bool:
    """Return whether ``signature`` is valid for ``message`` under the public key.

    The private key is not an input. A failure, including a missing openssl
    binary, is an invalid signature rather than a pass.
    """
    if not public_key_pem or "PRIVATE KEY" in public_key_pem:
        return False
    try:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            public_path = directory / "public.pem"
            message_path = directory / "message.bin"
            signature_path = directory / "signature.bin"
            public_path.write_text(public_key_pem, encoding="utf-8")
            message_path.write_bytes(message)
            signature_path.write_bytes(signature)
            result = subprocess.run(
                [
                    "openssl", "pkeyutl", "-verify",
                    "-pubin", "-inkey", str(public_path),
                    "-rawin", "-in", str(message_path),
                    "-sigfile", str(signature_path),
                ],
                capture_output=True,
                check=False,
            )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def verify_approval_record(
    approval: Any,
    *,
    team_id: str,
    endpoint: str,
    payload: Mapping[str, Any],
    public_key_pem: str,
    now: datetime,
) -> str:
    """Validate a signed approval. Return the nonce. Do not consume it."""
    record = _as_record(approval)
    try:
        signed_team = str(record["team_id"])
        signed_endpoint = str(record["endpoint"])
        signed_body = str(record["body_sha256"])
        nonce = str(record["nonce"])
        expires_at = str(record["expires_at"])
        signature = base64.b64decode(str(record["signature"]), validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise ExecutionDenied("approval record is malformed") from exc

    actual_body = payload_sha256(payload)
    if (
        signed_team != str(team_id)
        or signed_endpoint != endpoint
        or signed_body != actual_body
    ):
        raise ExecutionDenied("approval does not match this change")

    try:
        expiry = parse_expiry(expires_at)
    except ValueError as exc:
        raise ExecutionDenied("approval expiry is malformed") from exc
    if now >= expiry:
        raise ExecutionDenied("approval has expired")

    message = binding_bytes(
        team_id=signed_team,
        endpoint=signed_endpoint,
        body_sha256=signed_body,
        nonce=nonce,
        expires_at=expires_at,
    )
    if not verify_signature(public_key_pem, message, signature):
        raise ExecutionDenied("approval signature is not valid")
    return nonce


def load_public_key_pem(explicit: Optional[str] = None) -> str:
    """Load the verify-only public key. Never reads the signing key."""
    if explicit:
        return explicit
    path = os.environ.get("FPL_APPROVAL_PUBLIC_KEY", "").strip()
    if not path:
        raise ExecutionDenied("FPL_APPROVAL_PUBLIC_KEY is not set")
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ExecutionDenied("approval public key could not be read") from exc


class NonceStore:
    """Single-use nonce ledger. ``consume`` succeeds once per nonce."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def consume(self, nonce: str) -> bool:
        if not nonce or any(char not in "0123456789abcdef" for char in nonce):
            return False
        path = self.directory / nonce
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        os.close(fd)
        return True


def default_nonce_store() -> NonceStore:
    override = os.environ.get("FPL_APPROVAL_NONCE_DIR", "").strip()
    directory = Path(override) if override else Path.home() / ".cache" / "fpl-skill" / "approval-nonces"
    return NonceStore(directory)


def _as_record(approval: Any) -> Mapping[str, Any]:
    if isinstance(approval, str):
        text = approval.strip()
        if not text.startswith("{"):
            raise ExecutionDenied("missing out-of-band approval record")
        try:
            approval = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ExecutionDenied("approval record is malformed") from exc
    if not isinstance(approval, Mapping):
        raise ExecutionDenied("missing out-of-band approval record")
    return approval
