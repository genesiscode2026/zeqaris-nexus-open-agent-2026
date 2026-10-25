//! ZEQARIS NEXUS — ICP Canister Core
//! Handles Event Batch Verification, Certified State Commitment, and Threshold-ECDSA Voucher Signing.

use ic_cdk::{export_candid, init, post_upgrade, pre_upgrade, query, storage, update};

mod eip712;
mod state;

pub use eip712::SettlementVoucher;
pub use state::{
    BatchSubmission, CanisterStableState, CertifiedCheckpointQuery, CheckpointReceipt,
    EventEnvelope, SettlementAuthorizationRequest, SettlementAuthorizationResponse,
};

#[init]
fn init() {
    ic_cdk::println!("ZEQARIS NEXUS Canister initialized");
}

#[pre_upgrade]
fn pre_upgrade() {
    let stable = state::save_stable_state();
    storage::stable_save((stable,)).expect("Failed to save stable state");
}

#[post_upgrade]
fn post_upgrade() {
    let (stable,): (state::CanisterStableState,) =
        storage::stable_restore().expect("Failed to restore stable state");
    state::restore_stable_state(stable);
}

#[update]
fn verify_checkpoint_batch(
    batch: state::BatchSubmission,
) -> Result<state::CheckpointReceipt, String> {
    state::process_batch(batch)
}

#[update]
async fn authorize_settlement(
    req: state::SettlementAuthorizationRequest,
) -> Result<state::SettlementAuthorizationResponse, String> {
    state::authorize_settlement_voucher(req).await
}

#[query]
fn prepare_settlement(
    req: state::SettlementAuthorizationRequest,
) -> Result<state::SettlementAuthorizationResponse, String> {
    let (voucher, struct_hash, digest) = state::prepare_settlement_digest(&req)?;
    Ok(state::SettlementAuthorizationResponse {
        epoch: req.epoch,
        settlement_nonce: voucher.settlement_nonce,
        struct_hash: format!("0x{}", hex::encode(struct_hash)),
        digest: format!("0x{}", hex::encode(digest)),
        signature: "".to_string(),
        recovery_id: 0,
        status: "VOUCHER_DIGEST_PREPARED".to_string(),
    })
}

#[query]
fn get_certified_checkpoint_witness() -> state::CertifiedCheckpointQuery {
    state::get_certified_checkpoint_witness()
}

export_candid!();

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_canonical_jcs_reconstruction() {
        let ev = EventEnvelope {
            protocol_version: 1,
            schema_version: 1,
            environment: "base-sepolia".to_string(),
            swarm_id: "0x7a3f00000000000000000000000000000000000000000000000000000000b891"
                .to_string(),
            task_id: "task-001".to_string(),
            actor_id: "agent-alpha".to_string(),
            actor_key_id: "0x1111111111111111111111111111111111111111".to_string(),
            sequence: "1".to_string(),
            previous_event_hash:
                "0x0000000000000000000000000000000000000000000000000000000000000000".to_string(),
            event_type: "TASK_CREATED".to_string(),
            canonical_payload_hash:
                "0xe3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855".to_string(),
            policy_version_hash:
                "0x9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08".to_string(),
            timestamp_logical: "1729891200000".to_string(),
            nonce: "0".to_string(),
            signature: "0x3045".to_string(),
        };

        let jcs = state::reconstruct_canonical_jcs(&ev);
        assert!(jcs.starts_with("{\"actorId\":"));
        assert!(jcs.contains("\"schemaVersion\":1"));
    }

    #[test]
    fn test_eip712_domain_separator_vector() {
        let dom =
            eip712::compute_domain_separator(84532, "0x1111111111111111111111111111111111111111")
                .expect("Valid domain separator");
        assert_eq!(
            format!("0x{}", hex::encode(dom)),
            "0xa3b990f858e64be02b02d2ce6e107dec3ef94f0aca4a7b546be2e9282c8f9415"
        );
    }

    #[test]
    fn test_eip712_voucher_digest_vector() {
        let mut merkle_bytes = [0u8; 32];
        let clean_merkle =
            hex::decode("a43b40ecb7c44aadb1d98bd36ec108e05fa7b18650a8f645a6d66cd45bb7b929")
                .unwrap();
        merkle_bytes.copy_from_slice(&clean_merkle);

        let mut policy_bytes = [0u8; 32];
        let clean_policy =
            hex::decode("9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08")
                .unwrap();
        policy_bytes.copy_from_slice(&clean_policy);

        let voucher = eip712::SettlementVoucher {
            settlement_nonce: 1,
            epoch: 1,
            checkpoint_root: [0u8; 32],
            merkle_root: merkle_bytes,
            gross_amount: 100000,
            agent_net_total: 95000,
            royalty_amount: 5000,
            remainder_before: 0,
            remainder_after: 0,
            valid_after: 1729891200,
            deadline: 1729894800,
            policy_hash: policy_bytes,
        };

        let struct_hash = eip712::compute_voucher_struct_hash(&voucher).expect("Valid struct hash");
        assert_eq!(
            format!("0x{}", hex::encode(struct_hash)),
            "0x7d1034b29a332701a42d84c3c7dcbcb19c73505a3db059c05fb51fb5b63d4b9f"
        );

        let dom =
            eip712::compute_domain_separator(84532, "0x1111111111111111111111111111111111111111")
                .unwrap();
        let digest = eip712::compute_eip712_digest(dom, struct_hash);
        assert_eq!(
            format!("0x{}", hex::encode(digest)),
            "0x47c915d60303e423f121bcc661c3da9610d5d8ade2a858b392b664a858cc4e03"
        );
    }

    #[test]
    fn test_secp256k1_signature_recovery() {
        use sha2::Digest;
        use sha2::Sha256;

        let sig_bytes = hex::decode("e7db7efa3cb12acad06193f5c1057e8e19ddbca6d6af701eb7c046dbb9f8a3eb4249ff7f62571683c45c1287b3416b28a2981933e969d6259d356f61714fe9361c").unwrap();
        let sig = k256::ecdsa::Signature::try_from(&sig_bytes[0..64]).unwrap();
        let recid = k256::ecdsa::RecoveryId::from_byte(sig_bytes[64] - 27).unwrap();
        let hash = Sha256::digest(b"ZEQARIS test message");
        let vk = k256::ecdsa::VerifyingKey::recover_from_prehash(&hash, &sig, recid).unwrap();
        let uncompressed = vk.to_encoded_point(false);
        let raw_pub = &uncompressed.as_bytes()[1..65];
        let addr_hash = eip712::keccak256_hash(raw_pub);
        let addr = format!("0x{}", hex::encode(&addr_hash[12..32]));
        assert_eq!(addr, "0x2c7536e3605d9c16a7a3d7b1898e529396a65c23");
    }

    #[test]
    fn test_golden_vector_secp256k1_positive() {
        let hash = hex::decode("7ed69073daefd9ea30549f744caabe6dff9a08b342b30509f4e2ce70a923dbea")
            .unwrap();
        let mut event_hash = [0u8; 32];
        event_hash.copy_from_slice(&hash);

        let sig = "0x13a074459dfe8b3e116b1b7661710b9e88fefe9eb1a60ddf780a5236c96fd1735866d21397103327c83af4aa866e303238e8c98e4486d3a97c40e3177089ff901b";
        let actor = "0x2c7536e3605d9c16a7a3d7b1898e529396a65c23";

        let res = state::verify_actor_signature(&event_hash, sig, actor);
        assert!(res.is_ok(), "Expected valid signature verification to pass");
    }

    #[test]
    fn test_golden_vector_secp256k1_high_s_rejected() {
        let hash = hex::decode("7ed69073daefd9ea30549f744caabe6dff9a08b342b30509f4e2ce70a923dbea")
            .unwrap();
        let mut event_hash = [0u8; 32];
        event_hash.copy_from_slice(&hash);

        let high_s_sig = "0x13a074459dfe8b3e116b1b7661710b9e88fefe9eb1a60ddf780a5236c96fd173a7992dec68efccd837c50b557991cfcc81c613586ac1cc9243917b755fac41b11a";
        let actor = "0x2c7536e3605d9c16a7a3d7b1898e529396a65c23";

        let res = state::verify_actor_signature(&event_hash, high_s_sig, actor);
        assert_eq!(res.unwrap_err(), "ZEQARIS: HIGH_S_SIGNATURE_FORBIDDEN");
    }

    #[test]
    fn test_golden_vector_secp256k1_truncated_rejected() {
        let hash = hex::decode("7ed69073daefd9ea30549f744caabe6dff9a08b342b30509f4e2ce70a923dbea")
            .unwrap();
        let mut event_hash = [0u8; 32];
        event_hash.copy_from_slice(&hash);

        let trunc_sig = "0x13a074459dfe8b3e116b1b7661710b9e88fefe9eb1a60ddf780a5236c96fd1735866d21397103327c83af4aa866e303238e8c98e4486d3a97c40e3177089ff90";
        let actor = "0x2c7536e3605d9c16a7a3d7b1898e529396a65c23";

        let res = state::verify_actor_signature(&event_hash, trunc_sig, actor);
        assert_eq!(
            res.unwrap_err(),
            "ZEQARIS: SIGNATURE_LENGTH_MUST_BE_65_BYTES_HEX130"
        );
    }

    #[test]
    fn test_golden_vector_secp256k1_wrong_actor_rejected() {
        let hash = hex::decode("7ed69073daefd9ea30549f744caabe6dff9a08b342b30509f4e2ce70a923dbea")
            .unwrap();
        let mut event_hash = [0u8; 32];
        event_hash.copy_from_slice(&hash);

        let sig = "0x13a074459dfe8b3e116b1b7661710b9e88fefe9eb1a60ddf780a5236c96fd1735866d21397103327c83af4aa866e303238e8c98e4486d3a97c40e3177089ff901b";
        let wrong_actor = "0x1111111111111111111111111111111111111111";

        let res = state::verify_actor_signature(&event_hash, sig, wrong_actor);
        assert!(res
            .unwrap_err()
            .contains("ZEQARIS: ERR_ACTOR_SIGNATURE_MISMATCH"));
    }

    #[test]
    fn test_checkpoint_settlement_commitment_enforcement() {
        let comm = state::SettlementCommitment {
            epoch: 1,
            checkpoint_root: [0u8; 32],
            merkle_root: [2u8; 32],
            gross_amount: 100_000,
            agent_net_total: 95_000,
            royalty_amount: 5_000,
            remainder_before: 0,
            remainder_after: 0,
            valid_after: 100,
            deadline: 1000,
            policy_hash: [3u8; 32],
            chain_id: 84532,
            verifying_contract: "0x1111111111111111111111111111111111111111".to_string(),
        };
        state::test_helpers::set_test_epoch(1);
        state::test_helpers::set_test_commitment(comm);

        // An uncommitted request (e.g. wrong Merkle root) is rejected fail-closed
        let req_uncommitted = state::SettlementAuthorizationRequest {
            epoch: 1,
            merkle_root: "0x9999999999999999999999999999999999999999999999999999999999999999"
                .to_string(),
            gross_amount: 100_000,
            agent_net_total: 95_000,
            royalty_amount: 5_000,
            remainder_before: 0,
            remainder_after: 0,
            valid_after: 100,
            deadline: 1000,
            policy_hash: format!("0x{}", hex::encode([3u8; 32])),
            chain_id: 84532,
            verifying_contract: "0x1111111111111111111111111111111111111111".to_string(),
        };
        let err = state::prepare_settlement_digest(&req_uncommitted).unwrap_err();
        assert_eq!(
            err,
            "ZEQARIS: SETTLEMENT_REQUEST_DOES_NOT_MATCH_CHECKPOINT_COMMITMENT"
        );
    }
}
