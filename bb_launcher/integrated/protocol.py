"""Versioned JSON-lines protocol envelope for the integrated backend.

Stdout is protocol-only; logs use stderr/files.  Every request and every
response/event carries ``protocol``, ``op``/``ok``, ``id`` (operation id)
and ``seq`` (sequence number).  The backend is spawned with an argument
array, never a shell.  Passwords travel in request bodies only (never in
argv), are never logged, and optional persistence uses the OS credential
store -- which this backend does not implement; it holds secrets in
memory for the owning session only.

The protocol cannot run arbitrary commands: ``op`` is drawn from OPERATIONS.
"""

from __future__ import annotations

from typing import Any, Mapping

PROTOCOL_VERSION = "bb-ap-integration-v1"

OPERATIONS = (
    "capabilities",
    "inspect_install",
    "inspect_seed",
    "prepare_play",
    "verify_and_arm",
    "connect_and_start_client",
    "session_status",
    "stop_client",
    "cancel_operation",
)

# Stable machine-readable error codes.  Qt maps these to player-facing copy;
# the backend never invents player prose here beyond ``detail``.
ERROR_CODES = (
    "bad-request",
    "incompatible-protocol",
    "unknown-operation",
    "unsupported-build",
    "missing-prerequisite",
    "ambiguous-install",
    "ambiguous-player",
    "seed-identity-mismatch",
    "verification-failed",
    "conflict",
    "interrupted",
    "cancelled",
    "stale-session",
    "duplicate-client",
    "preflight-required",
    "internal-error",
)


class ProtocolError(Exception):
    def __init__(self, code: str, detail: str, *, retryable: bool = False,
                 recovery: tuple[str, ...] = (), ids: Mapping[str, str] | None = None):
        if code not in ERROR_CODES:
            raise ValueError(f"unknown protocol error code: {code}")
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.retryable = retryable
        self.recovery = tuple(recovery)
        self.ids = dict(ids or {})


def check_request(raw: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProtocolError("bad-request", "request must be a JSON object")
    if raw.get("protocol") != PROTOCOL_VERSION:
        raise ProtocolError(
            "incompatible-protocol",
            f"backend speaks {PROTOCOL_VERSION}; request said {raw.get('protocol')!r}",
        )
    op = raw.get("op")
    if op not in OPERATIONS:
        raise ProtocolError("unknown-operation", f"unsupported operation: {op!r}")
    if not isinstance(raw.get("id"), str) or not raw["id"]:
        raise ProtocolError("bad-request", "request requires a non-empty string id")
    if not isinstance(raw.get("seq"), int) or raw["seq"] < 0:
        raise ProtocolError("bad-request", "request requires a non-negative integer seq")
    params = raw.get("params", {})
    if not isinstance(params, dict):
        raise ProtocolError("bad-request", "request params must be an object")
    return {"protocol": raw["protocol"], "op": op, "id": raw["id"],
            "seq": raw["seq"], "params": dict(params)}


def ok_response(request_id: str, seq: int, result: Mapping[str, Any]) -> dict[str, Any]:
    return {"protocol": PROTOCOL_VERSION, "ok": True, "id": request_id,
            "seq": seq, "result": dict(result)}


def error_response(request_id: str, seq: int, error: ProtocolError) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL_VERSION,
        "ok": False,
        "id": request_id,
        "seq": seq,
        "error": {
            "code": error.code,
            "detail": error.detail,
            "retryable": error.retryable,
            "recovery": list(error.recovery),
            "ids": dict(error.ids),
        },
    }


def redact_for_log(value: Any) -> Any:
    """Strip secret fields before anything reaches logs or diagnostics."""

    if isinstance(value, dict):
        return {
            key: ("<redacted>" if key.casefold() in {"password", "passwd", "secret", "token"}
                  else redact_for_log(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_for_log(item) for item in value]
    return value
