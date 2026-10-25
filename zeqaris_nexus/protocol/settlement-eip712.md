# ZEQARIS Settlement Voucher Specification (EIP-712)

## 1. Abstract
This specification defines the EIP-712 typed structured data signature used by the Internet Computer (ICP) Canister via Threshold-ECDSA (`secp256k1`) to authorize epoch settlements on Base EVM.

## 2. EIP-712 Domain Separator
```solidity
struct EIP712Domain {
    string name;              // "ZEQARIS NEXUS Settlement Engine"
    string version;           // "1"
    uint256 chainId;          // e.g. 8453 (Base Mainnet) or 84532 (Base Sepolia)
    address verifyingContract;// ZeqarisSettlementEscrow contract address
}
```

## 3. SettlementVoucher Struct
```solidity
struct SettlementVoucher {
    uint256 settlementNonce;  // Strictly sequential nonce (+1 from current contract state)
    uint256 epoch;            // Epoch identifier
    bytes32 checkpointRoot;   // Canister certified checkpoint state root
    bytes32 merkleRoot;       // Merkle root of cumulative agent entitlements
    uint256 grossAmount;      // Total escrow gross funding in micro-USDC (6 decimals)
    uint256 agentNetTotal;    // Declared net micro-USDC available to agents
    uint256 royaltyAmount;    // 500 bps (5%) royalty micro-USDC
    uint256 remainderBefore;  // Sub-micro-USDC remainder carried from prior epoch
    uint256 remainderAfter;   // Sub-micro-USDC remainder carried to next epoch
    uint48 validAfter;        // Earliest timestamp for execution
    uint48 deadline;          // Latest timestamp for execution
    bytes32 policyHash;       // Hash of verified constitutional governance rules
}
```

## 4. Mathematical Verification Rules in Contract
1. Time bounds: `block.timestamp >= validAfter && block.timestamp <= deadline`
2. Nonce monotonicity: `voucher.settlementNonce == settlementNonce + 1`
3. Remainder continuity: `voucher.remainderBefore == accumulatedRemainder`
4. Exact 500 bps formula:
   $$\text{scaled} = (\text{grossAmount} \times 500) + \text{remainderBefore}$$
   $$\text{royaltyAmount} == \lfloor \text{scaled} / 10000 \rfloor$$
   $$\text{remainderAfter} == \text{scaled} \pmod{10000}$$
5. Conservation of value:
   $$\text{agentNetTotal} + \text{royaltyAmount} == \text{grossAmount}$$
6. Signature validity: `ecrecover(digest, v, r, s) == rootPublisher`
