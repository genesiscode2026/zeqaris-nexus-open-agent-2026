use candid::{CandidType, Deserialize};
use serde::Serialize;
use tiny_keccak::{Hasher, Keccak};

#[derive(Clone, Debug, CandidType, Deserialize, Serialize)]
pub struct SettlementVoucher {
    pub settlement_nonce: u64,
    pub epoch: u64,
    pub checkpoint_root: [u8; 32],
    pub merkle_root: [u8; 32],
    pub gross_amount: u128,
    pub agent_net_total: u128,
    pub royalty_amount: u128,
    pub remainder_before: u64,
    pub remainder_after: u64,
    pub valid_after: u64,
    pub deadline: u64,
    pub policy_hash: [u8; 32],
}

pub fn keccak256_hash(data: &[u8]) -> [u8; 32] {
    let mut keccak = Keccak::v256();
    keccak.update(data);
    let mut out = [0u8; 32];
    keccak.finalize(&mut out);
    out
}

pub fn compute_domain_separator(
    chain_id: u64,
    verifying_contract: &str,
) -> Result<[u8; 32], String> {
    let type_hash = keccak256_hash(
        b"EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)",
    );
    let name_hash = keccak256_hash(b"ZEQARIS NEXUS Settlement Engine");
    let version_hash = keccak256_hash(b"1");

    if chain_id == 0 {
        return Err("ZEQARIS: INVALID_CHAIN_ID".to_string());
    }

    if !verifying_contract.starts_with("0x") {
        return Err("ZEQARIS: CONTRACT_ADDRESS_MUST_START_WITH_0X".to_string());
    }

    let clean_addr = &verifying_contract[2..];
    if clean_addr.len() != 40 {
        return Err("ZEQARIS: CONTRACT_ADDRESS_HEX_LENGTH_MUST_BE_40".to_string());
    }

    let addr_bytes =
        hex::decode(clean_addr).map_err(|_| "ZEQARIS: INVALID_CONTRACT_HEX".to_string())?;
    if addr_bytes == [0u8; 20] {
        return Err("ZEQARIS: ZERO_ADDRESS_VERIFYING_CONTRACT_FORBIDDEN".to_string());
    }
    let mut addr_padded = [0u8; 32];
    addr_padded[12..32].copy_from_slice(&addr_bytes);

    let mut chain_id_padded = [0u8; 32];
    chain_id_padded[24..32].copy_from_slice(&chain_id.to_be_bytes());

    let mut buf = Vec::with_capacity(32 * 5);
    buf.extend_from_slice(&type_hash);
    buf.extend_from_slice(&name_hash);
    buf.extend_from_slice(&version_hash);
    buf.extend_from_slice(&chain_id_padded);
    buf.extend_from_slice(&addr_padded);

    Ok(keccak256_hash(&buf))
}

pub fn compute_voucher_struct_hash(v: &SettlementVoucher) -> Result<[u8; 32], String> {
    let max_uint48: u64 = (1u64 << 48) - 1;
    if v.valid_after > max_uint48 || v.deadline > max_uint48 {
        return Err("ZEQARIS: TIMESTAMP_EXCEEDS_UINT48".to_string());
    }
    if v.deadline < v.valid_after {
        return Err("ZEQARIS: DEADLINE_BEFORE_VALID_AFTER".to_string());
    }

    let type_hash = keccak256_hash(b"SettlementVoucher(uint256 settlementNonce,uint256 epoch,bytes32 checkpointRoot,bytes32 merkleRoot,uint256 grossAmount,uint256 agentNetTotal,uint256 royaltyAmount,uint256 remainderBefore,uint256 remainderAfter,uint48 validAfter,uint48 deadline,bytes32 policyHash)");

    let mut nonce_buf = [0u8; 32];
    nonce_buf[24..32].copy_from_slice(&v.settlement_nonce.to_be_bytes());

    let mut epoch_buf = [0u8; 32];
    epoch_buf[24..32].copy_from_slice(&v.epoch.to_be_bytes());

    let mut gross_buf = [0u8; 32];
    gross_buf[16..32].copy_from_slice(&v.gross_amount.to_be_bytes());

    let mut agent_buf = [0u8; 32];
    agent_buf[16..32].copy_from_slice(&v.agent_net_total.to_be_bytes());

    let mut royalty_buf = [0u8; 32];
    royalty_buf[16..32].copy_from_slice(&v.royalty_amount.to_be_bytes());

    let mut rem_before_buf = [0u8; 32];
    rem_before_buf[24..32].copy_from_slice(&v.remainder_before.to_be_bytes());

    let mut rem_after_buf = [0u8; 32];
    rem_after_buf[24..32].copy_from_slice(&v.remainder_after.to_be_bytes());

    let mut valid_after_buf = [0u8; 32];
    valid_after_buf[26..32].copy_from_slice(&v.valid_after.to_be_bytes()[2..8]);

    let mut deadline_buf = [0u8; 32];
    deadline_buf[26..32].copy_from_slice(&v.deadline.to_be_bytes()[2..8]);

    let mut buf = Vec::with_capacity(32 * 13);
    buf.extend_from_slice(&type_hash);
    buf.extend_from_slice(&nonce_buf);
    buf.extend_from_slice(&epoch_buf);
    buf.extend_from_slice(&v.checkpoint_root);
    buf.extend_from_slice(&v.merkle_root);
    buf.extend_from_slice(&gross_buf);
    buf.extend_from_slice(&agent_buf);
    buf.extend_from_slice(&royalty_buf);
    buf.extend_from_slice(&rem_before_buf);
    buf.extend_from_slice(&rem_after_buf);
    buf.extend_from_slice(&valid_after_buf);
    buf.extend_from_slice(&deadline_buf);
    buf.extend_from_slice(&v.policy_hash);

    Ok(keccak256_hash(&buf))
}

pub fn compute_eip712_digest(
    domain_separator: [u8; 32],
    voucher_struct_hash: [u8; 32],
) -> [u8; 32] {
    let mut buf = Vec::with_capacity(2 + 32 + 32);
    buf.extend_from_slice(b"\x19\x01");
    buf.extend_from_slice(&domain_separator);
    buf.extend_from_slice(&voucher_struct_hash);
    keccak256_hash(&buf)
}
