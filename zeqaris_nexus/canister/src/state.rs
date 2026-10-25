use candid::{CandidType, Deserialize};
use k256::ecdsa::{RecoveryId, Signature, VerifyingKey};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::cell::RefCell;

#[derive(Clone, Debug, CandidType, Deserialize, Serialize)]
pub struct EventEnvelope {
    pub protocol_version: u32,
    pub schema_version: u32,
    pub environment: String,
    pub swarm_id: String,
    pub task_id: String,
    pub actor_id: String,
    pub actor_key_id: String,
    pub sequence: String,
    pub previous_event_hash: String,
    pub event_type: String,
    pub canonical_payload_hash: String,
    pub policy_version_hash: String,
    pub timestamp_logical: String,
    pub nonce: String,
    pub signature: String,
}

#[derive(Clone, Debug, CandidType, Deserialize, Serialize, PartialEq, Eq)]
pub struct SettlementCommitment {
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
    pub chain_id: u64,
    pub verifying_contract: String,
}

#[derive(Clone, Debug, CandidType, Deserialize, Serialize)]
pub struct BatchSubmission {
    pub epoch: u64,
    pub events: Vec<EventEnvelope>,
    pub settlement_commitment: Option<SettlementCommitment>,
}

#[derive(Clone, Debug, CandidType, Deserialize, Serialize)]
pub struct CheckpointReceipt {
    pub epoch: u64,
    pub checkpoint_root: String,
    pub accepted_events_count: u64,
    pub last_sequence: u64,
    pub status: String,
}

#[derive(Clone, Debug, CandidType, Deserialize, Serialize)]
pub struct CertifiedCheckpointQuery {
    pub epoch: u64,
    pub checkpoint_root: String,
    pub certificate: Option<Vec<u8>>,
    pub last_sequence: u64,
}

#[derive(Clone, Debug, CandidType, Deserialize, Serialize)]
pub struct SettlementAuthorizationRequest {
    pub epoch: u64,
    pub merkle_root: String,
    pub gross_amount: u128,
    pub agent_net_total: u128,
    pub royalty_amount: u128,
    pub remainder_before: u64,
    pub remainder_after: u64,
    pub valid_after: u64,
    pub deadline: u64,
    pub policy_hash: String,
    pub chain_id: u64,
    pub verifying_contract: String,
}

#[derive(Clone, Debug, CandidType, Deserialize, Serialize)]
pub struct SettlementAuthorizationResponse {
    pub epoch: u64,
    pub settlement_nonce: u64,
    pub struct_hash: String,
    pub digest: String,
    pub signature: String,
    pub recovery_id: u8,
    pub status: String,
}

#[derive(Clone, Debug, CandidType, Deserialize, Serialize)]
pub struct CanisterStableState {
    pub state_version: u32,
    pub last_event_hash: [u8; 32],
    pub last_certified_root: [u8; 32],
    pub last_sequence: u64,
    pub last_epoch: u64,
    pub settlement_nonce: u64,
    pub pending_auth_key: Option<[u8; 32]>,
    pub last_auth_response: Option<SettlementAuthorizationResponse>,
    pub committed_settlement: Option<SettlementCommitment>,
}

thread_local! {
    static LAST_EVENT_HASH: RefCell<[u8; 32]> = const { RefCell::new([0u8; 32]) };
    static LAST_CERTIFIED_ROOT: RefCell<[u8; 32]> = const { RefCell::new([0u8; 32]) };
    static LAST_SEQUENCE: RefCell<u64> = const { RefCell::new(0) };
    static LAST_EPOCH: RefCell<u64> = const { RefCell::new(0) };
    static SETTLEMENT_NONCE: RefCell<u64> = const { RefCell::new(0) };
    static PENDING_AUTH_KEY: RefCell<Option<[u8; 32]>> = const { RefCell::new(None) };
    static LAST_AUTH_RESPONSE: RefCell<Option<SettlementAuthorizationResponse>> = const { RefCell::new(None) };
    static COMMITTED_SETTLEMENT: RefCell<Option<SettlementCommitment>> = const { RefCell::new(None) };
}

pub fn save_stable_state() -> CanisterStableState {
    CanisterStableState {
        state_version: 1,
        last_event_hash: LAST_EVENT_HASH.with(|h| *h.borrow()),
        last_certified_root: LAST_CERTIFIED_ROOT.with(|r| *r.borrow()),
        last_sequence: LAST_SEQUENCE.with(|s| *s.borrow()),
        last_epoch: LAST_EPOCH.with(|e| *e.borrow()),
        settlement_nonce: SETTLEMENT_NONCE.with(|n| *n.borrow()),
        pending_auth_key: PENDING_AUTH_KEY.with(|k| *k.borrow()),
        last_auth_response: LAST_AUTH_RESPONSE.with(|r| r.borrow().clone()),
        committed_settlement: COMMITTED_SETTLEMENT.with(|c| c.borrow().clone()),
    }
}

pub fn restore_stable_state(state: CanisterStableState) {
    LAST_EVENT_HASH.with(|h| *h.borrow_mut() = state.last_event_hash);
    LAST_CERTIFIED_ROOT.with(|r| *r.borrow_mut() = state.last_certified_root);
    LAST_SEQUENCE.with(|s| *s.borrow_mut() = state.last_sequence);
    LAST_EPOCH.with(|e| *e.borrow_mut() = state.last_epoch);
    SETTLEMENT_NONCE.with(|n| *n.borrow_mut() = state.settlement_nonce);
    PENDING_AUTH_KEY.with(|k| *k.borrow_mut() = state.pending_auth_key);
    LAST_AUTH_RESPONSE.with(|r| *r.borrow_mut() = state.last_auth_response);
    COMMITTED_SETTLEMENT.with(|c| *c.borrow_mut() = state.committed_settlement);
}

pub fn get_certified_checkpoint_witness() -> CertifiedCheckpointQuery {
    let root = LAST_CERTIFIED_ROOT.with(|r| *r.borrow());
    let epoch = LAST_EPOCH.with(|e| *e.borrow());
    let seq = LAST_SEQUENCE.with(|s| *s.borrow());
    let certificate = ic_cdk::api::data_certificate();

    CertifiedCheckpointQuery {
        epoch,
        checkpoint_root: format!("0x{}", hex::encode(root)),
        certificate,
        last_sequence: seq,
    }
}

pub fn reconstruct_canonical_jcs(ev: &EventEnvelope) -> String {
    format!(
        r#"{{"actorId":{},"actorKeyId":{},"canonicalPayloadHash":{},"environment":{},"eventType":{},"nonce":{},"policyVersionHash":{},"previousEventHash":{},"protocolVersion":{},"schemaVersion":{},"sequence":{},"swarmId":{},"taskId":{},"timestampLogical":{}}}"#,
        serde_json::to_string(&ev.actor_id).unwrap(),
        serde_json::to_string(&ev.actor_key_id).unwrap(),
        serde_json::to_string(&ev.canonical_payload_hash).unwrap(),
        serde_json::to_string(&ev.environment).unwrap(),
        serde_json::to_string(&ev.event_type).unwrap(),
        serde_json::to_string(&ev.nonce).unwrap(),
        serde_json::to_string(&ev.policy_version_hash).unwrap(),
        serde_json::to_string(&ev.previous_event_hash).unwrap(),
        ev.protocol_version,
        ev.schema_version,
        serde_json::to_string(&ev.sequence).unwrap(),
        serde_json::to_string(&ev.swarm_id).unwrap(),
        serde_json::to_string(&ev.task_id).unwrap(),
        serde_json::to_string(&ev.timestamp_logical).unwrap()
    )
}

fn is_canonical_decimal_string(s: &str) -> bool {
    if s.is_empty() {
        return false;
    }
    if s == "0" {
        return true;
    }
    if s.starts_with('0') {
        return false;
    }
    s.chars().all(|c| c.is_ascii_digit())
}

fn is_lowercase_hex_hash(s: &str, expected_len: usize) -> bool {
    if !s.starts_with("0x") {
        return false;
    }
    let raw = &s[2..];
    if raw.len() != expected_len {
        return false;
    }
    raw.chars()
        .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
}

fn is_valid_event_type(t: &str) -> bool {
    matches!(
        t,
        "TASK_CREATED"
            | "TASK_ASSIGNED"
            | "TASK_EXECUTING"
            | "TASK_COMPLETED"
            | "TASK_FAILED"
            | "SETTLEMENT_COMMITTED"
            | "EPOCH_FINALIZED"
    )
}

pub fn compute_commitment_hash(comm: &SettlementCommitment) -> [u8; 32] {
    let mut hasher = Sha256::new();
    hasher.update(b"ZEQARIS/PAYLOAD/V1\x00");
    hasher.update(comm.epoch.to_be_bytes());
    hasher.update(comm.checkpoint_root);
    hasher.update(comm.merkle_root);
    hasher.update(comm.gross_amount.to_be_bytes());
    hasher.update(comm.agent_net_total.to_be_bytes());
    hasher.update(comm.royalty_amount.to_be_bytes());
    hasher.update(comm.remainder_before.to_be_bytes());
    hasher.update(comm.remainder_after.to_be_bytes());
    hasher.update(comm.valid_after.to_be_bytes());
    hasher.update(comm.deadline.to_be_bytes());
    hasher.update(comm.policy_hash);
    hasher.update(comm.chain_id.to_be_bytes());
    hasher.update(comm.verifying_contract.as_bytes());
    hasher.finalize().into()
}

pub fn verify_actor_signature(
    event_hash: &[u8; 32],
    signature_hex: &str,
    expected_actor_key: &str,
) -> Result<(), String> {
    let clean_sig = signature_hex.strip_prefix("0x").unwrap_or(signature_hex);
    if clean_sig.len() != 130 {
        return Err("ZEQARIS: SIGNATURE_LENGTH_MUST_BE_65_BYTES_HEX130".to_string());
    }

    let sig_bytes =
        hex::decode(clean_sig).map_err(|_| "ZEQARIS: INVALID_SIGNATURE_HEX".to_string())?;

    let sig = Signature::try_from(&sig_bytes[0..64])
        .map_err(|_| "ZEQARIS: INVALID_SIGNATURE_R_S".to_string())?;

    if sig.normalize_s().is_some() {
        return Err("ZEQARIS: HIGH_S_SIGNATURE_FORBIDDEN".to_string());
    }

    let v_byte = sig_bytes[64];
    let recid_byte = match v_byte {
        0 | 1 => v_byte,
        27 | 28 => v_byte - 27,
        _ => return Err("ZEQARIS: INVALID_RECOVERY_ID_V".to_string()),
    };
    let recid = RecoveryId::from_byte(recid_byte)
        .ok_or_else(|| "ZEQARIS: INVALID_RECOVERY_ID".to_string())?;

    let vk = VerifyingKey::recover_from_prehash(event_hash, &sig, recid)
        .map_err(|_| "ZEQARIS: SIGNATURE_RECOVERY_FAILED".to_string())?;

    let uncompressed = vk.to_encoded_point(false);
    let raw_pub = &uncompressed.as_bytes()[1..65];
    let addr_hash = crate::eip712::keccak256_hash(raw_pub);
    let recovered_addr = format!("0x{}", hex::encode(&addr_hash[12..32]));
    let compressed_hex = hex::encode(vk.to_encoded_point(true).as_bytes());

    let clean_expected = expected_actor_key.to_lowercase();
    if clean_expected != recovered_addr.to_lowercase()
        && clean_expected != format!("0x{}", compressed_hex)
        && clean_expected != compressed_hex
    {
        return Err(format!(
            "ZEQARIS: ERR_ACTOR_SIGNATURE_MISMATCH: expected {}, recovered {}",
            expected_actor_key, recovered_addr
        ));
    }

    Ok(())
}

pub fn process_batch(batch: BatchSubmission) -> Result<CheckpointReceipt, String> {
    if batch.events.is_empty() {
        return Err("ZEQARIS: EMPTY_BATCH_REJECTED".to_string());
    }
    if batch.events.len() > 1000 {
        return Err("ZEQARIS: BATCH_SIZE_EXCEEDS_MAX_1000".to_string());
    }

    let mut current_last_hash = LAST_EVENT_HASH.with(|h| *h.borrow());
    let mut current_seq = LAST_SEQUENCE.with(|s| *s.borrow());
    let last_epoch = LAST_EPOCH.with(|e| *e.borrow());

    if batch.epoch <= last_epoch {
        return Err("ZEQARIS: NON_MONOTONIC_EPOCH_SEQUENCE".to_string());
    }

    let mut batch_hasher = Sha256::new();
    batch_hasher.update(b"ZEQARIS/CHECKPOINT/V1\x00");

    let mut settlement_event_found = false;

    for ev in &batch.events {
        if ev.protocol_version != 1 || ev.schema_version != 1 {
            return Err("ZEQARIS: UNSUPPORTED_PROTOCOL_VERSION".to_string());
        }

        if ev.environment != "base-sepolia" && ev.environment != "base-mainnet" {
            return Err("ZEQARIS: INVALID_ENVIRONMENT".to_string());
        }

        if !is_valid_event_type(&ev.event_type) {
            return Err("ZEQARIS: INVALID_EVENT_TYPE".to_string());
        }

        if ev.task_id.is_empty() || !ev.task_id.is_ascii() || ev.task_id.len() > 128 {
            return Err("ZEQARIS: INVALID_TASK_ID".to_string());
        }
        if ev.actor_id.is_empty() || !ev.actor_id.is_ascii() || ev.actor_id.len() > 128 {
            return Err("ZEQARIS: INVALID_ACTOR_ID".to_string());
        }

        if !is_lowercase_hex_hash(&ev.swarm_id, 64) {
            return Err("ZEQARIS: SWARM_ID_NOT_LOWERCASE_HEX64".to_string());
        }

        if !is_canonical_decimal_string(&ev.sequence) {
            return Err("ZEQARIS: SEQUENCE_NOT_CANONICAL_DECIMAL".to_string());
        }
        if !is_canonical_decimal_string(&ev.timestamp_logical) {
            return Err("ZEQARIS: TIMESTAMP_NOT_CANONICAL_DECIMAL".to_string());
        }
        if !is_canonical_decimal_string(&ev.nonce) {
            return Err("ZEQARIS: NONCE_NOT_CANONICAL_DECIMAL".to_string());
        }

        if !is_lowercase_hex_hash(&ev.previous_event_hash, 64) {
            return Err("ZEQARIS: PREVIOUS_HASH_NOT_LOWERCASE_HEX64".to_string());
        }
        if !is_lowercase_hex_hash(&ev.canonical_payload_hash, 64) {
            return Err("ZEQARIS: PAYLOAD_HASH_NOT_LOWERCASE_HEX64".to_string());
        }
        if !is_lowercase_hex_hash(&ev.policy_version_hash, 64) {
            return Err("ZEQARIS: POLICY_HASH_NOT_LOWERCASE_HEX64".to_string());
        }

        let ev_seq: u64 = ev
            .sequence
            .parse()
            .map_err(|_| "ZEQARIS: SEQUENCE_PARSE_ERROR")?;
        if ev_seq != current_seq + 1 {
            return Err(format!(
                "ZEQARIS: SEQUENCE_GAP: expected {}, got {}",
                current_seq + 1,
                ev_seq
            ));
        }

        let prev_hash_bytes = hex::decode(ev.previous_event_hash.trim_start_matches("0x"))
            .map_err(|_| "ZEQARIS: INVALID_HEX_PREVIOUS_HASH")?;
        if prev_hash_bytes.as_slice() != current_last_hash.as_slice() {
            return Err("ZEQARIS: HASH_CHAIN_CONTINUITY_BROKEN".to_string());
        }

        let canonical_jcs = reconstruct_canonical_jcs(ev);
        let mut event_hasher = Sha256::new();
        event_hasher.update(b"ZEQARIS/EVENT/V1\x00");
        event_hasher.update(canonical_jcs.as_bytes());
        let event_hash: [u8; 32] = event_hasher.finalize().into();

        verify_actor_signature(&event_hash, &ev.signature, &ev.actor_key_id)?;

        if ev.event_type == "SETTLEMENT_COMMITTED" {
            settlement_event_found = true;
            let commitment = batch
                .settlement_commitment
                .as_ref()
                .ok_or_else(|| "ZEQARIS: MISSING_SETTLEMENT_COMMITMENT_PAYLOAD".to_string())?;

            if commitment.epoch != batch.epoch {
                return Err("ZEQARIS: COMMITMENT_EPOCH_MISMATCH".to_string());
            }

            let computed_comm_hash = compute_commitment_hash(commitment);
            let expected_comm_hex = format!("0x{}", hex::encode(computed_comm_hash));
            if ev.canonical_payload_hash.to_lowercase() != expected_comm_hex.to_lowercase() {
                return Err("ZEQARIS: COMMITMENT_PAYLOAD_HASH_MISMATCH".to_string());
            }

            COMMITTED_SETTLEMENT.with(|c| *c.borrow_mut() = Some(commitment.clone()));
        }

        current_last_hash = event_hash;
        current_seq = ev_seq;
        batch_hasher.update(current_last_hash);
    }

    if !settlement_event_found && batch.settlement_commitment.is_some() {
        return Err("ZEQARIS: UNATTACHED_SETTLEMENT_COMMITMENT_WITHOUT_EVENT".to_string());
    }

    let checkpoint_root: [u8; 32] = batch_hasher.finalize().into();

    ic_cdk::api::set_certified_data(&checkpoint_root);

    LAST_EVENT_HASH.with(|h| *h.borrow_mut() = current_last_hash);
    LAST_CERTIFIED_ROOT.with(|r| *r.borrow_mut() = checkpoint_root);
    LAST_SEQUENCE.with(|s| *s.borrow_mut() = current_seq);
    LAST_EPOCH.with(|e| *e.borrow_mut() = batch.epoch);

    Ok(CheckpointReceipt {
        epoch: batch.epoch,
        checkpoint_root: format!("0x{}", hex::encode(checkpoint_root)),
        accepted_events_count: batch.events.len() as u64,
        last_sequence: current_seq,
        status: "ANCHORED_AND_CERTIFIED".to_string(),
    })
}

pub fn prepare_settlement_digest(
    req: &SettlementAuthorizationRequest,
) -> Result<(crate::eip712::SettlementVoucher, [u8; 32], [u8; 32]), String> {
    if req.epoch == 0 {
        return Err("ZEQARIS: ZERO_EPOCH_FORBIDDEN".to_string());
    }

    if req.chain_id != 8453 && req.chain_id != 84532 {
        return Err("ZEQARIS: CHAIN_ID_NOT_ALLOWLISTED".to_string());
    }

    let last_epoch = LAST_EPOCH.with(|e| *e.borrow());
    let last_root = LAST_CERTIFIED_ROOT.with(|r| *r.borrow());

    if req.epoch != last_epoch {
        return Err("ZEQARIS: EPOCH_NOT_YET_CERTIFIED".to_string());
    }

    let clean_merkle = hex::decode(req.merkle_root.trim_start_matches("0x"))
        .map_err(|_| "ZEQARIS: INVALID_MERKLE_ROOT_HEX")?;
    if clean_merkle.len() != 32 {
        return Err("ZEQARIS: MERKLE_ROOT_MUST_BE_EXACTLY_32_BYTES".to_string());
    }

    let clean_policy = hex::decode(req.policy_hash.trim_start_matches("0x"))
        .map_err(|_| "ZEQARIS: INVALID_POLICY_HASH_HEX")?;
    if clean_policy.len() != 32 {
        return Err("ZEQARIS: POLICY_HASH_MUST_BE_EXACTLY_32_BYTES".to_string());
    }

    let mut merkle_bytes = [0u8; 32];
    let mut policy_bytes = [0u8; 32];
    merkle_bytes.copy_from_slice(&clean_merkle);
    policy_bytes.copy_from_slice(&clean_policy);

    // Hard gate: Settlement MUST be anchored in checkpoint consensus
    let committed = COMMITTED_SETTLEMENT
        .with(|c| c.borrow().clone())
        .ok_or_else(|| "ZEQARIS: NO_SETTLEMENT_COMMITTED_IN_CHECKPOINT".to_string())?;

    if committed.epoch != req.epoch
        || committed.merkle_root != merkle_bytes
        || committed.gross_amount != req.gross_amount
        || committed.agent_net_total != req.agent_net_total
        || committed.royalty_amount != req.royalty_amount
        || committed.remainder_before != req.remainder_before
        || committed.remainder_after != req.remainder_after
        || committed.valid_after != req.valid_after
        || committed.deadline != req.deadline
        || committed.policy_hash != policy_bytes
        || committed.chain_id != req.chain_id
        || committed.verifying_contract.to_lowercase() != req.verifying_contract.to_lowercase()
    {
        return Err("ZEQARIS: SETTLEMENT_REQUEST_DOES_NOT_MATCH_CHECKPOINT_COMMITMENT".to_string());
    }

    if req.gross_amount == 0 {
        return Err("ZEQARIS: GROSS_AMOUNT_ZERO".to_string());
    }
    if req.agent_net_total.checked_add(req.royalty_amount) != Some(req.gross_amount) {
        return Err("ZEQARIS: CONSERVATION_OF_VALUE_VIOLATED".to_string());
    }

    let scaled = req
        .gross_amount
        .checked_mul(500)
        .and_then(|v| v.checked_add(req.remainder_before as u128))
        .ok_or_else(|| "ZEQARIS: ARITHMETIC_OVERFLOW".to_string())?;

    let expected_royalty = scaled / 10000;
    let expected_remainder_after = (scaled % 10000) as u64;

    if req.royalty_amount != expected_royalty {
        return Err("ZEQARIS: ROYALTY_AMOUNT_MISMATCH".to_string());
    }
    if req.remainder_after != expected_remainder_after {
        return Err("ZEQARIS: REMAINDER_AFTER_MISMATCH".to_string());
    }

    let max_uint48: u64 = (1u64 << 48) - 1;
    if req.valid_after > max_uint48 || req.deadline > max_uint48 {
        return Err("ZEQARIS: TIMESTAMP_EXCEEDS_UINT48".to_string());
    }
    if req.deadline < req.valid_after {
        return Err("ZEQARIS: DEADLINE_BEFORE_VALID_AFTER".to_string());
    }

    let domain_separator =
        crate::eip712::compute_domain_separator(req.chain_id, &req.verifying_contract)?;

    let predicted_nonce = SETTLEMENT_NONCE.with(|n| *n.borrow()) + 1;

    let voucher = crate::eip712::SettlementVoucher {
        settlement_nonce: predicted_nonce,
        epoch: req.epoch,
        checkpoint_root: last_root,
        merkle_root: merkle_bytes,
        gross_amount: req.gross_amount,
        agent_net_total: req.agent_net_total,
        royalty_amount: req.royalty_amount,
        remainder_before: req.remainder_before,
        remainder_after: req.remainder_after,
        valid_after: req.valid_after,
        deadline: req.deadline,
        policy_hash: policy_bytes,
    };

    let struct_hash = crate::eip712::compute_voucher_struct_hash(&voucher)?;
    let digest = crate::eip712::compute_eip712_digest(domain_separator, struct_hash);

    Ok((voucher, struct_hash, digest))
}

#[cfg(not(test))]
pub async fn sign_threshold_ecdsa(
    digest: &[u8; 32],
    key_name: &str,
) -> Result<(String, u8), String> {
    use ic_cdk::api::management_canister::ecdsa::{
        ecdsa_public_key, sign_with_ecdsa, EcdsaCurve, EcdsaKeyId, EcdsaPublicKeyArgument,
        SignWithEcdsaArgument,
    };

    let key_id = EcdsaKeyId {
        curve: EcdsaCurve::Secp256k1,
        name: key_name.to_string(),
    };
    let derivation_path = vec![b"zeqaris_settlement".to_vec()];

    let (pubkey_res,) = ecdsa_public_key(EcdsaPublicKeyArgument {
        canister_id: None,
        derivation_path: derivation_path.clone(),
        key_id: key_id.clone(),
    })
    .await
    .map_err(|(code, msg)| format!("ICP ecdsa_public_key failed [{:?}]: {}", code, msg))?;

    let (sign_res,) = sign_with_ecdsa(SignWithEcdsaArgument {
        message_hash: digest.to_vec(),
        derivation_path,
        key_id,
    })
    .await
    .map_err(|(code, msg)| format!("ICP sign_with_ecdsa failed [{:?}]: {}", code, msg))?;

    let raw_sig = sign_res.signature;
    if raw_sig.len() != 64 {
        return Err("ZEQARIS: INVALID_T_ECDSA_SIG_LENGTH".to_string());
    }

    let sig = Signature::try_from(&raw_sig[0..64])
        .map_err(|_| "ZEQARIS: INVALID_T_ECDSA_R_S".to_string())?;

    let sig_low = sig.normalize_s().unwrap_or(sig);

    let mut matching_recid = None;
    for candidate_v in [0u8, 1u8] {
        if let Some(recid) = RecoveryId::from_byte(candidate_v) {
            if let Ok(vk) = VerifyingKey::recover_from_prehash(digest, &sig_low, recid) {
                if vk.to_encoded_point(true).as_bytes() == pubkey_res.public_key.as_slice() {
                    matching_recid = Some(candidate_v);
                    break;
                }
            }
        }
    }

    let recid =
        matching_recid.ok_or_else(|| "ZEQARIS: FAILED_MATCHING_T_ECDSA_PUBLIC_KEY".to_string())?;

    let mut sig_65 = [0u8; 65];
    sig_65[0..64].copy_from_slice(&sig_low.to_bytes());
    sig_65[64] = recid + 27;

    Ok((format!("0x{}", hex::encode(sig_65)), recid))
}

#[cfg(test)]
pub async fn sign_threshold_ecdsa(
    digest: &[u8; 32],
    _key_name: &str,
) -> Result<(String, u8), String> {
    test_helpers::sign_test_digest(digest)
}

#[cfg(test)]
#[allow(clippy::items_after_test_module)]
pub mod test_helpers {
    use super::*;

    pub fn set_test_commitment(comm: SettlementCommitment) {
        COMMITTED_SETTLEMENT.with(|c| *c.borrow_mut() = Some(comm));
    }

    pub fn set_test_epoch(epoch: u64) {
        LAST_EPOCH.with(|e| *e.borrow_mut() = epoch);
    }

    pub fn sign_test_digest(digest: &[u8; 32]) -> Result<(String, u8), String> {
        let key_bytes =
            hex::decode("0000000000000000000000000000000000000000000000000000000000000b0b")
                .map_err(|_| "Failed key hex".to_string())?;
        let signing_key = k256::ecdsa::SigningKey::from_bytes(key_bytes.as_slice().into())
            .map_err(|_| "Failed signing key".to_string())?;

        let (sig, recid) = signing_key
            .sign_prehash_recoverable(digest)
            .map_err(|_| "Threshold signing failed".to_string())?;

        let sig_low = sig.normalize_s().unwrap_or(sig);
        let mut sig_bytes = [0u8; 65];
        sig_bytes[0..64].copy_from_slice(&sig_low.to_bytes());
        sig_bytes[64] = recid.to_byte() + 27;

        Ok((format!("0x{}", hex::encode(sig_bytes)), recid.to_byte()))
    }
}

pub async fn authorize_settlement_voucher(
    req: SettlementAuthorizationRequest,
) -> Result<SettlementAuthorizationResponse, String> {
    let (voucher, struct_hash, digest) = prepare_settlement_digest(&req)?;

    let mut idem_input = Vec::with_capacity(72);
    idem_input.extend_from_slice(&req.epoch.to_be_bytes());
    idem_input.extend_from_slice(&voucher.merkle_root);
    idem_input.extend_from_slice(&voucher.policy_hash);
    let idem_key = crate::eip712::keccak256_hash(&idem_input);

    if let Some(cached) = LAST_AUTH_RESPONSE.with(|r| r.borrow().clone()) {
        if cached.epoch == req.epoch && cached.digest == format!("0x{}", hex::encode(digest)) {
            return Ok(cached);
        }
    }

    if let Some(pending) = PENDING_AUTH_KEY.with(|k| *k.borrow()) {
        if pending == idem_key {
            return Err("ZEQARIS: IN_PROGRESS".to_string());
        } else {
            return Err("ZEQARIS: CONCURRENT_SETTLEMENT_IN_PROGRESS".to_string());
        }
    }

    PENDING_AUTH_KEY.with(|k| *k.borrow_mut() = Some(idem_key));

    let sign_result = sign_threshold_ecdsa(&digest, "key_1").await;

    match sign_result {
        Ok((signature_hex, recid)) => {
            let committed_nonce = voucher.settlement_nonce;
            SETTLEMENT_NONCE.with(|n| *n.borrow_mut() = committed_nonce);
            PENDING_AUTH_KEY.with(|k| *k.borrow_mut() = None);

            let resp = SettlementAuthorizationResponse {
                epoch: req.epoch,
                settlement_nonce: committed_nonce,
                struct_hash: format!("0x{}", hex::encode(struct_hash)),
                digest: format!("0x{}", hex::encode(digest)),
                signature: signature_hex,
                recovery_id: recid,
                status: "VOUCHER_THRESHOLD_SIGNED".to_string(),
            };

            LAST_AUTH_RESPONSE.with(|r| *r.borrow_mut() = Some(resp.clone()));
            Ok(resp)
        }
        Err(e) => {
            PENDING_AUTH_KEY.with(|k| *k.borrow_mut() = None);
            Err(e)
        }
    }
}
