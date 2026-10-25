# ZEQARIS-JCS-1: Canonical Serialization Specification
**Normative Profile of RFC 8785 (JSON Canonicalization Scheme)**

## 1. Scope and Objective
This specification defines the exact, deterministic canonical encoding rules for event envelopes exchanged between edge coordinators (Cloudflare Workers / Durable Objects) and threshold validators (Internet Computer Protocol canisters).

## 2. Normative Profile Constraints
1. **UTF-8 Encoding:** All JSON documents must be valid UTF-8 without BOM.
2. **Key Ordering:** Object keys must be sorted lexicographically by UTF-16 code units as mandated by RFC 8785 Section 3.2.3.
3. **Number Restrictions:**
   - Floating-point representations, exponents (`e`, `E`), `NaN`, `Infinity`, and `-0` are strictly forbidden.
   - All critical domain numbers (amounts, sequence numbers, timestamps, nonces) must be represented as decimal strings.
   - Decimal strings must conform to regex `^(0|[1-9][0-9]*)$` (leading zeros are strictly rejected).
4. **Binary & Hash Representation:**
   - Hashes must be represented as lowercase hexadecimal strings prefixed with `0x`.
   - Raw binary payloads must be encoded as unpadded Base64URL.
5. **Payload Decoupling:**
   - Large or arbitrary agent/human payloads must never be embedded unconstrained in the event envelope.
   - The envelope carries only `canonicalPayloadHash = SHA-256("ZEQARIS/PAYLOAD/V1\0" || rawPayloadBytes)`.
6. **Domain Separation Prefix:**
   - The canonical event hash is computed as:
     $$\text{eventHash} = \text{SHA-256}\Big(\text{UTF-8}(\text{"ZEQARIS/EVENT/V1\textbackslash 0"}) \;\Vert\; \text{JCS}(\text{envelopeWithoutSignature})\Big)$$

## 3. Envelope Schema (13 Normative Fields)
| Field | Type | Description |
| :--- | :--- | :--- |
| `protocolVersion` | `integer` | Must be `1` |
| `schemaVersion` | `integer` | Must be `1` |
| `environment` | `string` | `"base-sepolia"` or `"base-mainnet"` |
| `swarmId` | `string` | Lowercase hex `0x` + 64 hex characters |
| `taskId` | `string` | ASCII identifier |
| `actorId` | `string` | ASCII identifier |
| `actorKeyId` | `string` | DID or hex public key |
| `sequence` | `string` | Monotonic decimal string |
| `previousEventHash`| `string` | Lowercase hex `0x` + 64 hex characters |
| `eventType` | `string` | One of `TASK_CREATED`, `TASK_ASSIGNED`, `TASK_COMPLETED`, etc. |
| `canonicalPayloadHash`| `string` | SHA-256 hash of payload |
| `policyVersionHash`| `string` | SHA-256 hash of active constitutional rules |
| `timestampLogical` | `string` | Unix timestamp in milliseconds as decimal string |
| `nonce` | `string` | Decimal string |
