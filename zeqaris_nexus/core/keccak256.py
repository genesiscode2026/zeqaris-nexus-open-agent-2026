"""
Pure Python Ethereum Keccak-256 Implementation
Matches Solidity / EVM keccak256 exactly.
"""

def keccak256(data: bytes) -> bytes:
    RC = [
        0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
        0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
        0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
        0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
        0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
        0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008
    ]
    rot = [
        [0, 36, 3, 41, 18], [1, 44, 10, 45, 2], [62, 6, 43, 15, 61],
        [28, 55, 25, 21, 56], [27, 20, 39, 8, 14]
    ]
    rate = 136
    padding_len = rate - (len(data) % rate)
    if padding_len == 1:
        padded = data + b'\x81'
    else:
        padded = data + b'\x01' + b'\x00' * (padding_len - 2) + b'\x80'
    state = [0] * 25
    for b in range(0, len(padded), rate):
        block = padded[b:b+rate]
        for i in range(17):
            val = int.from_bytes(block[i*8:(i+1)*8], 'little')
            state[i] ^= val
        for round_idx in range(24):
            C = [state[x] ^ state[x+5] ^ state[x+10] ^ state[x+15] ^ state[x+20] for x in range(5)]
            D = [C[(x+4)%5] ^ (((C[(x+1)%5] << 1) | (C[(x+1)%5] >> 63)) & 0xFFFFFFFFFFFFFFFF) for x in range(5)]
            for i in range(25):
                state[i] ^= D[i % 5]
            B = [0] * 25
            for x in range(5):
                for y in range(5):
                    idx = x + 5 * y
                    r = rot[x][y]
                    B[y + 5 * ((2*x + 3*y) % 5)] = ((state[idx] << r) | (state[idx] >> (64 - r))) & 0xFFFFFFFFFFFFFFFF if r else state[idx]
            for x in range(5):
                for y in range(5):
                    state[x + 5*y] = B[x + 5*y] ^ ((~B[(x+1)%5 + 5*y]) & B[(x+2)%5 + 5*y]) & 0xFFFFFFFFFFFFFFFF
            state[0] ^= RC[round_idx]
    out = bytearray()
    for i in range(4):
        out.extend(state[i].to_bytes(8, 'little'))
    return bytes(out)
