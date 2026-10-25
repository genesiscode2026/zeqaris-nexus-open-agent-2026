// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/**
 * @title ZeqarisSettlementEscrow
 * @author ZEQARIS NEXUS Architecture Core
 * @notice Immutable Escrow, EIP-712 Voucher Verification & Cumulative Merkle Settlement Engine on Base L2.
 * 
 * CORE ARCHITECTURAL INVARIANTS:
 * 1. Royalty Invariant: Strictly 500 bps (5.00%) of gross funding directed to FOUNDER_WALLET.
 * 2. Precision Invariant: Remainder Accumulator captures sub-micro-USDC fractions (0..9999 units) across epochs:
 *    500 * Σ(gross) + remainder_0 = 10000 * Σ(royalty) + remainder_current (0 <= remainder < 10000).
 * 3. Value Conservation Invariant: grossAmount == agentNetTotal + royaltyAmount.
 * 4. Liveness Invariant: Royalty is accrued via pull-payment (claimRoyalty), preventing blacklist/revert DoS on the swarm.
 * 5. Least Privilege: GUARDIAN can only pause; RESOLVER (timelock/multisig) can unpause/cancel; neither has fund custody.
 * 6. Transport Decoupling: ICP Canister signs EIP-712 SettlementVouchers; relayers submit permissionlessly without EVM nonce lock.
 * 7. Single Active Pending Epoch: Prevents multi-voucher escrow over-reservation. Mutations occur at finalizeEpoch.
 * 8. Non-Zero Epoch Sentinel: epoch == 0 is strictly forbidden to preserve activePendingEpoch == 0 sentinel integrity.
 * 9. Fail-Closed Accounting: Reverts if totalReservedClaims < payout.
 * 10. Low-S ECDSA Hardening: Rejects high-s and zero-address signatures.
 */

interface IERC20 {
    function totalSupply() external view returns (uint256);
    function balanceOf(address account) external view returns (uint256);
    function transfer(address to, uint256 value) external returns (bool);
    function allowance(address owner, address spender) external view returns (uint256);
    function transferFrom(address from, address to, uint256 value) external returns (bool);
}

library SafeERC20 {
    function safeTransfer(IERC20 token, address to, uint256 value) internal {
        require(to != address(0), "SafeERC20: transfer to zero address");
        (bool success, bytes memory data) = address(token).call(
            abi.encodeWithSelector(token.transfer.selector, to, value)
        );
        require(success && (data.length == 0 || abi.decode(data, (bool))), "SafeERC20: transfer failed");
    }

    function safeTransferFrom(IERC20 token, address from, address to, uint256 value) internal {
        require(to != address(0), "SafeERC20: transfer to zero address");
        (bool success, bytes memory data) = address(token).call(
            abi.encodeWithSelector(token.transferFrom.selector, from, to, value)
        );
        require(success && (data.length == 0 || abi.decode(data, (bool))), "SafeERC20: transferFrom failed");
    }
}

library MerkleProof {
    function verify(bytes32[] memory proof, bytes32 root, bytes32 leaf) internal pure returns (bool) {
        bytes32 computedHash = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            bytes32 proofElement = proof[i];
            if (computedHash <= proofElement) {
                computedHash = keccak256(abi.encodePacked(computedHash, proofElement));
            } else {
                computedHash = keccak256(abi.encodePacked(proofElement, computedHash));
            }
        }
        return computedHash == root;
    }
}

abstract contract ReentrancyGuard {
    uint256 private constant _NOT_ENTERED = 1;
    uint256 private constant _ENTERED = 2;
    uint256 private _status;

    constructor() {
        _status = _NOT_ENTERED;
    }

    modifier nonReentrant() {
        require(_status != _ENTERED, "ReentrancyGuard: reentrant call");
        _status = _ENTERED;
        _;
        _status = _NOT_ENTERED;
    }
}

contract ZeqarisSettlementEscrow is ReentrancyGuard {
    using SafeERC20 for IERC20;

    // --- IMMUTABLE CONSTANTS ---
    uint256 public constant ROYALTY_BPS = 500;       // 5.00%
    uint256 public constant BPS_DENOMINATOR = 10000;
    uint256 public constant PUBLISHER_ROTATION_DELAY = 1 days;
    
    // Canonical Payment Rail Law: Base USDC Payout Wallet
    address public constant FOUNDER_WALLET = 0xC6F86e170411182114FcCdb28793dC76B5e8D144;
    
    IERC20 public immutable usdc;
    uint256 public immutable challengeWindowDuration; // e.g. 30s (testnet/demo) or 86400s (production)
    uint256 public immutable maxEpochGross;           // Cap on single epoch funding
    uint256 public immutable maxOutstandingLiabilities;// Safety ceiling on total unfinalized + unpaid liabilities

    // --- EIP-712 DOMAIN SEPARATOR & TYPEHASH ---
    bytes32 public immutable DOMAIN_SEPARATOR;
    bytes32 public constant SETTLEMENT_VOUCHER_TYPEHASH = keccak256(
        "SettlementVoucher(uint256 settlementNonce,uint256 epoch,bytes32 checkpointRoot,bytes32 merkleRoot,uint256 grossAmount,uint256 agentNetTotal,uint256 royaltyAmount,uint256 remainderBefore,uint256 remainderAfter,uint48 validAfter,uint48 deadline,bytes32 policyHash)"
    );

    // --- ROLES & GOVERNANCE ---
    address public rootPublisher; // ICP Canister Threshold-ECDSA public key
    address public pendingPublisher;
    uint256 public publisherTimelockExpiry;

    address public guardian;      // Multisig: pause/emergency veto only
    address public resolver;      // Timelock/Multisig: unpause, replace, cancel only
    address public admin;         // Role management only via timelock

    // --- ENUMS & STRUCTS ---
    enum EpochState { NONE, PENDING, FINALIZED, CANCELLED }

    struct EpochCommitment {
        bytes32 checkpointRoot;
        bytes32 merkleRoot;
        uint256 grossAmount;
        uint256 declaredAgentNetTotal;
        uint256 royaltyAmount;
        uint256 remainderBefore;
        uint256 remainderAfter;
        uint256 publishTimestamp;
        EpochState state;
        bool isPaused;
    }

    struct SettlementVoucher {
        uint256 settlementNonce;
        uint256 epoch;
        bytes32 checkpointRoot;
        bytes32 merkleRoot;
        uint256 grossAmount;
        uint256 agentNetTotal;
        uint256 royaltyAmount;
        uint256 remainderBefore;
        uint256 remainderAfter;
        uint48 validAfter;
        uint48 deadline;
        bytes32 policyHash;
    }

    struct ClaimRequest {
        address account;
        uint256 cumulativeEntitlement;
        uint256 epoch;
        bytes32[] proof;
    }

    // --- STATE VARIABLES ---
    uint256 public activePendingEpoch;   // Single active pending epoch enforcement
    uint256 public accumulatedRemainder; // In sub-micro-USDC frac units (0..9999)
    uint256 public settlementNonce;
    uint256 public royaltyAccrued;        // Pull-payment escrow for Founder
    uint256 public totalReservedClaims;   // Sum of unpaid finalized agent entitlements
    bool public isGlobalPaused;

    mapping(uint256 => EpochCommitment) public epochs;
    mapping(address => uint256) public claimed; // agent => cumulative lifetime claimed amount

    // --- EVENTS ---
    event VoucherSubmitted(
        uint256 indexed epoch,
        uint256 indexed settlementNonce,
        bytes32 checkpointRoot,
        bytes32 merkleRoot,
        uint256 grossAmount,
        uint256 agentNetTotal,
        uint256 royaltyAmount,
        uint256 remainderAfter
    );
    event EpochFinalized(uint256 indexed epoch, bytes32 indexed merkleRoot, uint256 agentNetTotal, uint256 royaltyAccrued);
    event EpochPaused(uint256 indexed epoch, bytes32 indexed evidenceHash, address indexed guardian);
    event EpochUnpaused(uint256 indexed epoch, address indexed resolver);
    event EpochCancelled(uint256 indexed epoch, bytes32 indexed reasonHash, address indexed resolver);
    event RewardClaimed(
        address indexed account,
        address indexed recipient,
        uint256 indexed epoch,
        uint256 payout,
        uint256 newCumulativeClaimed
    );
    event RoyaltyClaimed(address indexed recipient, uint256 amount);
    event GlobalPauseToggled(bool isPaused, bytes32 evidenceHash);
    event PublisherRotationProposed(address indexed proposedPublisher, uint256 timelockExpiry);
    event PublisherRotationExecuted(address indexed oldPublisher, address indexed newPublisher);

    modifier onlyGuardian() {
        require(msg.sender == guardian, "ZEQARIS: NOT_GUARDIAN");
        _;
    }

    modifier onlyResolver() {
        require(msg.sender == resolver, "ZEQARIS: NOT_RESOLVER");
        _;
    }

    modifier onlyAdmin() {
        require(msg.sender == admin, "ZEQARIS: NOT_ADMIN");
        _;
    }

    modifier whenNotGlobalPaused() {
        require(!isGlobalPaused, "ZEQARIS: GLOBAL_PAUSED");
        _;
    }

    constructor(
        address _usdc,
        address _rootPublisher,
        address _guardian,
        address _resolver,
        uint256 _challengeWindowDuration,
        uint256 _maxEpochGross,
        uint256 _maxOutstandingLiabilities
    ) {
        require(_usdc != address(0), "ZEQARIS: ZERO_USDC_ADDRESS");
        require(_rootPublisher != address(0), "ZEQARIS: ZERO_PUBLISHER_ADDRESS");
        require(_guardian != address(0), "ZEQARIS: ZERO_GUARDIAN_ADDRESS");
        require(_resolver != address(0), "ZEQARIS: ZERO_RESOLVER_ADDRESS");
        require(_maxEpochGross > 0, "ZEQARIS: ZERO_MAX_EPOCH_GROSS");
        require(_maxOutstandingLiabilities >= _maxEpochGross, "ZEQARIS: INVALID_MAX_LIABILITIES");

        usdc = IERC20(_usdc);
        rootPublisher = _rootPublisher;
        guardian = _guardian;
        resolver = _resolver;
        admin = msg.sender;
        challengeWindowDuration = _challengeWindowDuration;
        maxEpochGross = _maxEpochGross;
        maxOutstandingLiabilities = _maxOutstandingLiabilities;

        DOMAIN_SEPARATOR = keccak256(
            abi.encode(
                keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)"),
                keccak256(bytes("ZEQARIS NEXUS Settlement Engine")),
                keccak256(bytes("1")),
                block.chainid,
                address(this)
            )
        );
    }

    /**
     * @notice Submits an EIP-712 SettlementVoucher authorized by ICP Canister Threshold-ECDSA.
     * @dev Modularized into internal helpers to prevent EVM stack-too-deep.
     */
    function submitSettlementVoucher(
        SettlementVoucher calldata voucher,
        bytes calldata signature
    ) external whenNotGlobalPaused nonReentrant {
        // 1. Structural preconditions
        require(voucher.epoch != 0, "ZEQARIS: ZERO_EPOCH_RESERVED");
        require(activePendingEpoch == 0, "ZEQARIS: ACTIVE_PENDING_EPOCH_EXISTS");
        require(epochs[voucher.epoch].state == EpochState.NONE, "ZEQARIS: EPOCH_ALREADY_EXISTS");
        require(voucher.merkleRoot != bytes32(0), "ZEQARIS: ZERO_MERKLE_ROOT");
        require(voucher.grossAmount > 0, "ZEQARIS: ZERO_GROSS_AMOUNT");
        require(voucher.settlementNonce == settlementNonce + 1, "ZEQARIS: INVALID_SETTLEMENT_NONCE");
        require(block.timestamp >= voucher.validAfter, "ZEQARIS: VOUCHER_NOT_YET_VALID");
        require(block.timestamp <= voucher.deadline, "ZEQARIS: VOUCHER_EXPIRED");

        // 2. Validate economic rules and solvency coverage
        _validateVoucherEconomics(voucher);

        // 3. Verify EIP-712 signature from ICP Threshold-ECDSA
        bytes32 structHash = _hashVoucher(voucher);
        _verifyVoucherSignature(structHash, signature);

        // 4. Record proposal without early financial mutation
        settlementNonce = voucher.settlementNonce;
        activePendingEpoch = voucher.epoch;

        epochs[voucher.epoch] = EpochCommitment({
            checkpointRoot: voucher.checkpointRoot,
            merkleRoot: voucher.merkleRoot,
            grossAmount: voucher.grossAmount,
            declaredAgentNetTotal: voucher.agentNetTotal,
            royaltyAmount: voucher.royaltyAmount,
            remainderBefore: voucher.remainderBefore,
            remainderAfter: voucher.remainderAfter,
            publishTimestamp: block.timestamp,
            state: EpochState.PENDING,
            isPaused: false
        });

        emit VoucherSubmitted(
            voucher.epoch,
            voucher.settlementNonce,
            voucher.checkpointRoot,
            voucher.merkleRoot,
            voucher.grossAmount,
            voucher.agentNetTotal,
            voucher.royaltyAmount,
            voucher.remainderAfter
        );
    }

    /**
     * @notice Helper to validate solvency, caps, remainder math, and conservation of value.
     */
    function _validateVoucherEconomics(
        SettlementVoucher calldata voucher
    ) internal view {
        require(voucher.grossAmount <= maxEpochGross, "ZEQARIS: EXCEEDS_MAX_EPOCH_GROSS");
        require(
            getAccountedLiabilities() + voucher.grossAmount <= maxOutstandingLiabilities,
            "ZEQARIS: EXCEEDS_MAX_OUTSTANDING_LIABILITIES"
        );
        require(
            usdc.balanceOf(address(this)) >= getAccountedLiabilities() + voucher.grossAmount,
            "ZEQARIS: INSUFFICIENT_ESCROW_BALANCE"
        );
        require(voucher.remainderBefore == accumulatedRemainder, "ZEQARIS: REMAINDER_BEFORE_MISMATCH");

        uint256 scaled = (voucher.grossAmount * ROYALTY_BPS) + accumulatedRemainder;
        uint256 expectedRoyalty = scaled / BPS_DENOMINATOR;
        uint256 expectedRemainderAfter = scaled % BPS_DENOMINATOR;

        require(voucher.royaltyAmount == expectedRoyalty, "ZEQARIS: VOUCHER_ROYALTY_MISMATCH");
        require(voucher.remainderAfter == expectedRemainderAfter, "ZEQARIS: VOUCHER_REMAINDER_MISMATCH");
        require(
            voucher.agentNetTotal + voucher.royaltyAmount == voucher.grossAmount,
            "ZEQARIS: CONSERVATION_OF_VALUE_VIOLATED"
        );
    }

    /**
     * @notice Helper to hash the EIP-712 SettlementVoucher struct.
     */
    function _hashVoucher(
        SettlementVoucher calldata voucher
    ) internal pure returns (bytes32) {
        return keccak256(
            abi.encode(
                SETTLEMENT_VOUCHER_TYPEHASH,
                voucher.settlementNonce,
                voucher.epoch,
                voucher.checkpointRoot,
                voucher.merkleRoot,
                voucher.grossAmount,
                voucher.agentNetTotal,
                voucher.royaltyAmount,
                voucher.remainderBefore,
                voucher.remainderAfter,
                voucher.validAfter,
                voucher.deadline,
                voucher.policyHash
            )
        );
    }

    /**
     * @notice Helper to verify recovered signer against rootPublisher.
     */
    function _verifyVoucherSignature(
        bytes32 structHash,
        bytes calldata signature
    ) internal view {
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", DOMAIN_SEPARATOR, structHash));
        address recoveredSigner = _recoverSigner(digest, signature);
        require(recoveredSigner == rootPublisher, "ZEQARIS: INVALID_ICP_SIGNATURE");
    }

    /**
     * @notice Finalizes an epoch after challenge window expires without veto.
     * @dev Mutates remainder, accrues royalty, and unlocks agent claims. Transition: PENDING -> FINALIZED.
     */
    function finalizeEpoch(uint256 epoch) external whenNotGlobalPaused nonReentrant {
        require(epoch == activePendingEpoch, "ZEQARIS: NOT_ACTIVE_PENDING_EPOCH");
        EpochCommitment storage commitment = epochs[epoch];
        require(commitment.state == EpochState.PENDING, "ZEQARIS: EPOCH_NOT_PENDING");
        require(!commitment.isPaused, "ZEQARIS: EPOCH_PAUSED_BY_GUARDIAN");
        require(
            block.timestamp >= commitment.publishTimestamp + challengeWindowDuration,
            "ZEQARIS: CHALLENGE_WINDOW_ACTIVE"
        );

        // Clear active pending slot
        activePendingEpoch = 0;

        // Apply financial mutations atomically at finalization
        accumulatedRemainder = commitment.remainderAfter;
        royaltyAccrued += commitment.royaltyAmount;
        totalReservedClaims += commitment.declaredAgentNetTotal;
        commitment.state = EpochState.FINALIZED;

        emit EpochFinalized(epoch, commitment.merkleRoot, commitment.declaredAgentNetTotal, royaltyAccrued);
    }

    /**
     * @notice Guardian can pause a contested epoch during the challenge window.
     */
    function pauseEpoch(uint256 epoch, bytes32 evidenceHash) external onlyGuardian {
        EpochCommitment storage commitment = epochs[epoch];
        require(commitment.state == EpochState.PENDING, "ZEQARIS: CANNOT_PAUSE_NON_PENDING");
        commitment.isPaused = true;
        emit EpochPaused(epoch, evidenceHash, msg.sender);
    }

    /**
     * @notice Resolver can unpause an epoch after investigating evidence.
     */
    function unpauseEpoch(uint256 epoch) external onlyResolver {
        EpochCommitment storage commitment = epochs[epoch];
        require(commitment.isPaused, "ZEQARIS: EPOCH_NOT_PAUSED");
        commitment.isPaused = false;
        emit EpochUnpaused(epoch, msg.sender);
    }

    /**
     * @notice Resolver can cancel an invalid epoch before finalization.
     * @dev Transition: PENDING -> CANCELLED. No financial rollback needed because mutations occur at finalize.
     */
    function cancelEpoch(uint256 epoch, bytes32 reasonHash) external onlyResolver {
        require(epoch == activePendingEpoch, "ZEQARIS: NOT_ACTIVE_PENDING_EPOCH");
        EpochCommitment storage commitment = epochs[epoch];
        require(commitment.state == EpochState.PENDING, "ZEQARIS: CANNOT_CANCEL_NON_PENDING");

        activePendingEpoch = 0;
        commitment.state = EpochState.CANCELLED;

        emit EpochCancelled(epoch, reasonHash, msg.sender);
    }

    /**
     * @notice Permissionless claim for an individual agent.
     */
    function claim(
        address account,
        uint256 cumulativeEntitlement,
        uint256 epoch,
        bytes32[] calldata proof
    ) external whenNotGlobalPaused nonReentrant returns (uint256) {
        return _executeClaim(account, account, cumulativeEntitlement, epoch, proof);
    }

    /**
     * @notice Sponsored claim execution: caller pays gas, funds go strictly to agent account.
     */
    function claimFor(
        address account,
        uint256 cumulativeEntitlement,
        uint256 epoch,
        bytes32[] calldata proof
    ) external whenNotGlobalPaused nonReentrant returns (uint256) {
        return _executeClaim(account, account, cumulativeEntitlement, epoch, proof);
    }

    /**
     * @notice Batch claim for multiple agents in a single transaction.
     */
    function claimBatch(ClaimRequest[] calldata requests) external whenNotGlobalPaused nonReentrant {
        for (uint256 i = 0; i < requests.length; i++) {
            _executeClaim(
                requests[i].account,
                requests[i].account,
                requests[i].cumulativeEntitlement,
                requests[i].epoch,
                requests[i].proof
            );
        }
    }

    /**
     * @notice Pull-payment royalty withdrawal: prevents DoS if Founder address is blacklisted.
     * @dev Paused under global emergency to freeze all fund outflows.
     */
    function claimRoyalty() external whenNotGlobalPaused nonReentrant returns (uint256) {
        uint256 toPay = royaltyAccrued;
        require(toPay > 0, "ZEQARIS: NO_ROYALTY_ACCRUED");

        royaltyAccrued = 0;
        usdc.safeTransfer(FOUNDER_WALLET, toPay);

        emit RoyaltyClaimed(FOUNDER_WALLET, toPay);
        return toPay;
    }

    function _executeClaim(
        address account,
        address recipient,
        uint256 cumulativeEntitlement,
        uint256 epoch,
        bytes32[] memory proof
    ) internal returns (uint256) {
        EpochCommitment storage commitment = epochs[epoch];
        require(commitment.state == EpochState.FINALIZED, "ZEQARIS: EPOCH_NOT_FINALIZED");
        require(!commitment.isPaused, "ZEQARIS: EPOCH_PAUSED");

        // Double-keccak leaf hashing prevents second-preimage collision attacks
        bytes32 leaf = keccak256(bytes.concat(keccak256(abi.encode(account, cumulativeEntitlement))));
        require(MerkleProof.verify(proof, commitment.merkleRoot, leaf), "ZEQARIS: INVALID_MERKLE_PROOF");

        uint256 previousClaimed = claimed[account];
        require(cumulativeEntitlement > previousClaimed, "ZEQARIS: NO_NEW_ENTITLEMENT");

        uint256 payout = cumulativeEntitlement - previousClaimed;
        
        // Fail-closed strict accounting check
        require(totalReservedClaims >= payout, "ZEQARIS: INSUFFICIENT_RESERVED_CLAIMS");
        totalReservedClaims -= payout;
        claimed[account] = cumulativeEntitlement;

        usdc.safeTransfer(recipient, payout);

        emit RewardClaimed(account, recipient, epoch, payout, cumulativeEntitlement);
        return payout;
    }

    function _recoverSigner(bytes32 digest, bytes calldata signature) internal pure returns (address) {
        require(signature.length == 65, "ZEQARIS: INVALID_SIG_LENGTH");
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 0x20))
            v := byte(0, calldataload(add(signature.offset, 0x40)))
        }
        if (v < 27) {
            v += 27;
        }
        require(v == 27 || v == 28, "ZEQARIS: INVALID_SIG_V");
        require(
            uint256(s) <= 0x7fffffffffffffffffffffffffffffff5d576e7357a4501ddfe92f46681b20a0,
            "ZEQARIS: INVALID_SIG_S"
        );
        address signer = ecrecover(digest, v, r, s);
        require(signer != address(0), "ZEQARIS: INVALID_SIGNER_ZERO");
        return signer;
    }

    // --- FINANCIAL SURPLUS ACCOUNTING ---
    function getAccountedLiabilities() public view returns (uint256) {
        return totalReservedClaims + royaltyAccrued;
    }

    function getSurplus() external view returns (uint256) {
        uint256 actualBalance = usdc.balanceOf(address(this));
        uint256 liabilities = getAccountedLiabilities();
        return actualBalance > liabilities ? actualBalance - liabilities : 0;
    }

    // --- EMERGENCY CIRCUIT BREAKER (GUARDIAN PAUSE ONLY / RESOLVER UNPAUSE) ---
    function triggerEmergencyPause(bytes32 evidenceHash) external onlyGuardian {
        require(!isGlobalPaused, "ZEQARIS: ALREADY_PAUSED");
        isGlobalPaused = true;
        emit GlobalPauseToggled(true, evidenceHash);
    }

    function liftEmergencyPause(bytes32 resolutionEvidence) external onlyResolver {
        require(isGlobalPaused, "ZEQARIS: NOT_PAUSED");
        isGlobalPaused = false;
        emit GlobalPauseToggled(false, resolutionEvidence);
    }

    // --- 2-STEP TIMELOCKED PUBLISHER ROTATION ---
    function proposePublisherRotation(address newPublisher) external onlyAdmin {
        require(newPublisher != address(0), "ZEQARIS: ZERO_ADDRESS");
        pendingPublisher = newPublisher;
        publisherTimelockExpiry = block.timestamp + PUBLISHER_ROTATION_DELAY;
        emit PublisherRotationProposed(newPublisher, publisherTimelockExpiry);
    }

    function executePublisherRotation() external onlyAdmin {
        require(pendingPublisher != address(0), "ZEQARIS: NO_PENDING_PUBLISHER");
        require(block.timestamp >= publisherTimelockExpiry, "ZEQARIS: TIMELOCK_ACTIVE");
        address old = rootPublisher;
        rootPublisher = pendingPublisher;
        pendingPublisher = address(0);
        emit PublisherRotationExecuted(old, rootPublisher);
    }
}
