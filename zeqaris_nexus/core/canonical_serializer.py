"""
ZEQARIS-JCS-1 Canonical Serialization Engine (RFC 8785 Compliant)
Part of ZEQARIS NEXUS — Autonomous Swarm Coordination & Escrow Settlement OS

Enforces strict RFC 8785 JSON Canonicalization Scheme with ZEQARIS-JCS-1 profile:
- UTF-8 deterministic serialization
- Lexicographical key sorting by UTF-16 code units (RFC 8785 section 3.2.3)
- Strict rejection of floats, NaN, Infinity, exponents, and -0
- Critical numeric values (amounts, sequences, nonces, timestamps) must be decimal strings
- Decimal strings must conform to: "0" | ^[1-9][0-9]*$ (no leading zeros)
- Hashes must be lowercase hex strings of exact expected length
- Rejection of unknown fields (strict schema validation)
- Domain separation prefix for event hashing
"""

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

class CanonicalizationError(ValueError):
    """Raised when JSON violates RFC 8785 or ZEQARIS-JCS-1 profile."""
    pass

VALID_EVENT_TYPES = {
    "TASK_CREATED",
    "TASK_ASSIGNED",
    "TASK_COMPLETED",
    "INVARIANT_CHECKPOINT",
    "DISPUTE_RAISED",
    "SETTLEMENT_PROPOSED"
}

ALLOWED_ENVELOPE_KEYS = {
    "protocolVersion",
    "schemaVersion",
    "environment",
    "swarmId",
    "taskId",
    "actorId",
    "actorKeyId",
    "sequence",
    "previousEventHash",
    "eventType",
    "canonicalPayloadHash",
    "policyVersionHash",
    "timestampLogical",
    "nonce",
    "signature"
}

REQUIRED_ENVELOPE_KEYS = ALLOWED_ENVELOPE_KEYS - {"signature"}

DOMAIN_EVENT_V1 = b"ZEQARIS/EVENT/V1\x00"
DOMAIN_PAYLOAD_V1 = b"ZEQARIS/PAYLOAD/V1\x00"

DECIMAL_STRING_PATTERN = re.compile(r"^(0|[1-9][0-9]*)$")
HEX_64_PATTERN = re.compile(r"^0x[0-9a-f]{64}$")
HEX_40_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")

MAX_UINT256 = (1 << 256) - 1

def reject_duplicate_keys(ordered_pairs):
    seen = set()
    d = {}
    for k, v in ordered_pairs:
        if k in seen:
            raise CanonicalizationError(f"Duplicate key rejected: {k}")
        seen.add(k)
        d[k] = v
    return d

def parse_canonical_json(raw_json_str: str) -> Any:
    # Check for raw negative zero token '-0'
    if re.search(r':\s*-0(\D|$)', raw_json_str):
        raise CanonicalizationError("Negative zero is forbidden in ZEQARIS-JCS-1 profile")
    return json.loads(raw_json_str, object_pairs_hook=reject_duplicate_keys)

def validate_decimal_string(val: Any, field_name: str) -> str:
    if not isinstance(val, str):
        raise CanonicalizationError(f"Field '{field_name}' must be a string, got {type(val).__name__}")
    if not DECIMAL_STRING_PATTERN.match(val):
        raise CanonicalizationError(f"Field '{field_name}' must be a valid decimal string without leading zeros: '{val}'")
    if int(val) > MAX_UINT256:
        raise CanonicalizationError(f"Field '{field_name}' exceeds maximum uint256 limit: '{val}'")
    return val


def validate_hex_hash(val: Any, field_name: str, expected_length: int = 64) -> str:
    if not isinstance(val, str):
        raise CanonicalizationError(f"Field '{field_name}' must be a string, got {type(val).__name__}")
    if not val.startswith("0x"):
        raise CanonicalizationError(f"Field '{field_name}' must start with '0x'")
    raw_hex = val[2:]
    if len(raw_hex) != expected_length:
        raise CanonicalizationError(f"Field '{field_name}' hex length must be {expected_length}, got {len(raw_hex)}")
    if raw_hex != raw_hex.lower():
        raise CanonicalizationError(f"Field '{field_name}' must be lowercase hex")
    try:
        int(raw_hex, 16)
    except ValueError:
        raise CanonicalizationError(f"Field '{field_name}' contains non-hex characters")
    return val


def to_utf16_code_units(s: str) -> List[int]:
    """Encodes string to UTF-16-BE and returns list of 16-bit code units (RFC 8785 §3.2.3)."""
    raw = s.encode("utf-16-be")
    return [int.from_bytes(raw[i:i+2], "big") for i in range(0, len(raw), 2)]

def canonicalize_jcs(obj: Any) -> bytes:
    """
    Serializes a Python object to canonical JSON bytes according to RFC 8785.
    Keys are sorted lexicographically by UTF-16 code units.
    Whitespace is completely removed.
    """
    if obj is None:
        return b"null"
    elif isinstance(obj, bool):
        return b"true" if obj else b"false"
    elif isinstance(obj, int):
        return str(obj).encode("utf-8")
    elif isinstance(obj, float):
        raise CanonicalizationError("Floating point numbers are forbidden in ZEQARIS-JCS-1 profile")
    elif isinstance(obj, str):
        escaped = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
        return escaped.encode("utf-8")
    elif isinstance(obj, list):
        items = [canonicalize_jcs(x) for x in obj]
        return b"[" + b",".join(items) + b"]"
    elif isinstance(obj, dict):
        # Sort keys lexicographically by UTF-16 code units as required by RFC 8785 Section 3.2.3
        sorted_keys = sorted(obj.keys(), key=to_utf16_code_units)
        pairs = []
        for k in sorted_keys:
            if not isinstance(k, str):
                raise CanonicalizationError(f"Dictionary keys must be strings, got {type(k).__name__}")
            k_bytes = canonicalize_jcs(k)
            v_bytes = canonicalize_jcs(obj[k])
            pairs.append(k_bytes + b":" + v_bytes)
        return b"{" + b",".join(pairs) + b"}"
    else:
        raise CanonicalizationError(f"Unsupported data type for canonicalization: {type(obj).__name__}")


def validate_and_normalize_envelope(raw_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates that the event envelope strictly matches ZEQARIS-JCS-1 profile.
    """
    # 1. Reject unknown keys
    unknown_keys = set(raw_dict.keys()) - ALLOWED_ENVELOPE_KEYS
    if unknown_keys:
        raise CanonicalizationError(f"Unknown keys rejected: {unknown_keys}")

    # 2. Check required fields
    missing_keys = REQUIRED_ENVELOPE_KEYS - set(raw_dict.keys())
    if missing_keys:
        raise CanonicalizationError(f"Missing required envelope keys: {missing_keys}")

    # 3. Protocol & Schema Version
    if raw_dict["protocolVersion"] != 1:
        raise CanonicalizationError(f"Unsupported protocolVersion: {raw_dict['protocolVersion']}")
    if raw_dict["schemaVersion"] != 1:
        raise CanonicalizationError(f"Unsupported schemaVersion: {raw_dict['schemaVersion']}")

    # 4. Strict field typing
    validate_decimal_string(raw_dict["sequence"], "sequence")
    validate_decimal_string(raw_dict["timestampLogical"], "timestampLogical")
    validate_decimal_string(raw_dict["nonce"], "nonce")
    
    validate_hex_hash(raw_dict["previousEventHash"], "previousEventHash", 64)
    validate_hex_hash(raw_dict["canonicalPayloadHash"], "canonicalPayloadHash", 64)
    validate_hex_hash(raw_dict["policyVersionHash"], "policyVersionHash", 64)

    if raw_dict["eventType"] not in VALID_EVENT_TYPES:
        raise CanonicalizationError(f"Invalid eventType: {raw_dict['eventType']}")

    # Strip signature if present for unsigned envelope hashing
    envelope_unsigned = {k: v for k, v in raw_dict.items() if k != "signature"}
    return envelope_unsigned


def compute_payload_hash(raw_payload_bytes: bytes) -> str:
    """Computes SHA-256( UTF8('ZEQARIS/PAYLOAD/V1\\0') || rawPayload )"""
    h = hashlib.sha256()
    h.update(DOMAIN_PAYLOAD_V1)
    h.update(raw_payload_bytes)
    return "0x" + h.hexdigest().lower()


def compute_event_hash(envelope_dict: Dict[str, Any]) -> str:
    """
    Computes SHA-256( UTF8('ZEQARIS/EVENT/V1\\0') || JCS(eventEnvelopeWithoutSignature) )
    """
    unsigned_envelope = validate_and_normalize_envelope(envelope_dict)
    canonical_bytes = canonicalize_jcs(unsigned_envelope)
    
    h = hashlib.sha256()
    h.update(DOMAIN_EVENT_V1)
    h.update(canonical_bytes)
    return "0x" + h.hexdigest().lower()
