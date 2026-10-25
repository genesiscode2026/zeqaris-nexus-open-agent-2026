"""
ZEQARIS NEXUS — Pure Python secp256k1 & ECDSA Module
Zero external dependencies. Compatible with Python 3.8+.
Provides RFC 6979 deterministic nonce generation, low-S signature generation (EIP-2),
public key recovery, and Ethereum address derivation.
"""

import hmac
import hashlib
from typing import Tuple, Optional
from .keccak256 import keccak256

# secp256k1 curve parameters
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
G = (GX, GY)


def point_add(p1: Optional[Tuple[int, int]], p2: Optional[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if x1 == x2:
        m = (3 * x1 * x1) * pow(2 * y1, -1, P) % P
    else:
        m = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (m * m - x1 - x2) % P
    y3 = (m * (x1 - x3) - y1) % P
    return (x3, y3)


def point_mul(k: int, point: Optional[Tuple[int, int]]) -> Optional[Tuple[int, int]]:
    res = None
    curr = point
    while k:
        if k & 1:
            res = point_add(res, curr)
        curr = point_add(curr, curr)
        k >>= 1
    return res


def rfc6979_nonce(msg_hash: bytes, privkey: int) -> int:
    """Deterministic nonce k generation per RFC 6979 using HMAC-SHA256."""
    x_bytes = privkey.to_bytes(32, "big")
    h1 = msg_hash
    V = b"\x01" * 32
    K = b"\x00" * 32
    K = hmac.new(K, V + b"\x00" + x_bytes + h1, hashlib.sha256).digest()
    V = hmac.new(K, V, hashlib.sha256).digest()
    K = hmac.new(K, V + b"\x01" + x_bytes + h1, hashlib.sha256).digest()
    V = hmac.new(K, V, hashlib.sha256).digest()
    while True:
        V = hmac.new(K, V, hashlib.sha256).digest()
        k = int.from_bytes(V, "big")
        if 1 <= k < N:
            return k
        K = hmac.new(K, V + b"\x00", hashlib.sha256).digest()
        V = hmac.new(K, V, hashlib.sha256).digest()


def sign_prehash_recoverable(privkey_hex: str, msg_hash: bytes) -> Tuple[bytes, int]:
    """
    Signs a 32-byte precomputed hash using secp256k1 ECDSA.
    Enforces strict Low-S (EIP-2) to guarantee anti-malleability.
    Returns (65_bytes_signature_with_v, recovery_id).
    """
    clean_key = privkey_hex[2:] if privkey_hex.startswith("0x") else privkey_hex
    privkey = int(clean_key, 16)
    if not (1 <= privkey < N):
        raise ValueError("Invalid private key: outside curve order bounds")

    k = rfc6979_nonce(msg_hash, privkey)
    R = point_mul(k, G)
    if R is None:
        raise RuntimeError("Failed computing R point")

    r = R[0] % N
    if r == 0:
        raise RuntimeError("r is zero, retry signing")

    z = int.from_bytes(msg_hash, "big")
    s = (pow(k, -1, N) * (z + r * privkey)) % N
    if s == 0:
        raise RuntimeError("s is zero, retry signing")

    recid = R[1] % 2
    # Strict Low-S enforcement (EIP-2)
    if s > N // 2:
        s = N - s
        recid ^= 1

    v = 27 + recid
    sig_65 = r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([v])
    return sig_65, recid


def private_key_to_address(privkey_hex: str) -> str:
    """Derives canonical lowercase 0x Ethereum address from private key."""
    clean_key = privkey_hex[2:] if privkey_hex.startswith("0x") else privkey_hex
    privkey = int(clean_key, 16)
    pub = point_mul(privkey, G)
    if pub is None:
        raise ValueError("Invalid private key: point at infinity")
    pub_bytes = pub[0].to_bytes(32, "big") + pub[1].to_bytes(32, "big")
    addr_hash = keccak256(pub_bytes)
    return "0x" + addr_hash[12:32].hex()


def private_key_to_compressed_pubkey(privkey_hex: str) -> str:
    """Derives 33-byte compressed public key hex (02/03 + X)."""
    clean_key = privkey_hex[2:] if privkey_hex.startswith("0x") else privkey_hex
    privkey = int(clean_key, 16)
    pub = point_mul(privkey, G)
    if pub is None:
        raise ValueError("Invalid private key")
    prefix = b"\x02" if pub[1] % 2 == 0 else b"\x03"
    return "0x" + (prefix + pub[0].to_bytes(32, "big")).hex()
