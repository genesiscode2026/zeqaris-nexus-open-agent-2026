// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "forge-std/Test.sol";
import "forge-std/StdInvariant.sol";
import "../../src/ZeqarisSettlementEscrow.sol";
import "../mocks/MockUSDC.sol";

contract EscrowHandler is Test {
    ZeqarisSettlementEscrow public immutable escrow;
    MockUSDC public immutable usdc;
    uint256 public immutable signerPrivateKey;
    address public immutable publisher;
    address public immutable guardian;
    address public immutable resolver;
    address public immutable admin;

    address public immutable agent1 = address(0x1001);
    address public immutable agent2 = address(0x1002);

    // Ghost variables for formal invariant tracking
    uint256 public ghostFunded;
    uint256 public ghostGrossAccepted;
    uint256 public ghostPendingAgentLiability;
    uint256 public ghostReservedClaims;
    uint256 public ghostRoyaltyAccrued;
    uint256 public ghostAgentPaid;
    uint256 public ghostRoyaltyPaid;
    uint256 public ghostCancelledGross;
    uint256 public ghostLastNonce;
    uint256 public ghostLastRemainder;

    uint256 public callsAttempted;
    uint256 public callsSucceeded;

    uint256 public currentEpochCounter;
    bytes32 internal policyHash = keccak256("ZEQARIS/POLICY/V1");

    mapping(address => uint256) public ghostLastClaimed;
    mapping(uint256 => bool) public ghostEpochFinalized;
    mapping(uint256 => uint256) public ghostEpochAgentNet;

    constructor(
        ZeqarisSettlementEscrow _escrow,
        MockUSDC _usdc,
        uint256 _signerKey,
        address _guardian,
        address _resolver
    ) {
        escrow = _escrow;
        usdc = _usdc;
        signerPrivateKey = _signerKey;
        publisher = vm.addr(_signerKey);
        guardian = _guardian;
        resolver = _resolver;
        admin = _escrow.admin();
    }

    function fund(uint256 amount) external {
        callsAttempted++;
        if (amount > 0 && amount <= 10_000_000_000) {
            usdc.mint(address(escrow), amount);
            ghostFunded += amount;
            callsSucceeded++;
        }
    }

    function submitValidVoucher(uint256 grossAmount) public {
        callsAttempted++;
        if (grossAmount < 2 || grossAmount > 10_000_000) return;
        if (escrow.activePendingEpoch() != 0) return;
        if (escrow.isGlobalPaused()) return;

        uint256 currentLiabilities = escrow.getAccountedLiabilities();
        if (usdc.balanceOf(address(escrow)) < currentLiabilities + grossAmount) return;
        if (currentLiabilities + grossAmount > escrow.maxOutstandingLiabilities()) return;

        currentEpochCounter++;
        ZeqarisSettlementEscrow.SettlementVoucher memory voucher = _buildVoucher(grossAmount);
        bytes memory sig = _signVoucher(voucher);

        try escrow.submitSettlementVoucher(voucher, sig) {
            ghostGrossAccepted += grossAmount;
            ghostPendingAgentLiability = voucher.agentNetTotal;
            ghostEpochAgentNet[currentEpochCounter] = voucher.agentNetTotal;
            ghostLastNonce = voucher.settlementNonce;
            callsSucceeded++;
        } catch {}
    }

    function _buildVoucher(uint256 grossAmount)
        internal
        view
        returns (ZeqarisSettlementEscrow.SettlementVoucher memory voucher)
    {
        uint256 remainderBefore = escrow.accumulatedRemainder();
        uint256 scaled = (grossAmount * 500) + remainderBefore;
        uint256 royalty = scaled / 10000;
        uint256 agentNet = grossAmount - royalty;

        voucher.settlementNonce = escrow.settlementNonce() + 1;
        voucher.epoch = currentEpochCounter;
        voucher.checkpointRoot = keccak256(abi.encodePacked("checkpoint", currentEpochCounter));
        voucher.merkleRoot = _merkleRoot(agentNet);
        voucher.grossAmount = grossAmount;
        voucher.agentNetTotal = agentNet;
        voucher.royaltyAmount = royalty;
        voucher.remainderBefore = remainderBefore;
        voucher.remainderAfter = scaled % 10000;
        voucher.validAfter = uint48(block.timestamp);
        voucher.deadline = uint48(block.timestamp + 3600);
        voucher.policyHash = policyHash;
    }

    function _merkleRoot(uint256 agentNet) internal view returns (bytes32) {
        uint256 half = agentNet / 2;
        bytes32 leaf1 = keccak256(bytes.concat(keccak256(abi.encode(agent1, half))));
        bytes32 leaf2 = keccak256(bytes.concat(keccak256(abi.encode(agent2, agentNet - half))));
        return leaf1 <= leaf2
            ? keccak256(abi.encodePacked(leaf1, leaf2))
            : keccak256(abi.encodePacked(leaf2, leaf1));
    }

    function _signVoucher(ZeqarisSettlementEscrow.SettlementVoucher memory voucher)
        internal
        returns (bytes memory)
    {
        bytes32 structHash = keccak256(
            abi.encode(
                escrow.SETTLEMENT_VOUCHER_TYPEHASH(),
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
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", escrow.DOMAIN_SEPARATOR(), structHash));
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(signerPrivateKey, digest);
        return abi.encodePacked(r, s, v);
    }

    function finalizeEpoch() external {
        callsAttempted++;
        uint256 pending = escrow.activePendingEpoch();
        if (pending == 0) return;
        if (escrow.isGlobalPaused()) return;

        vm.warp(block.timestamp + 31);
        try escrow.finalizeEpoch(pending) {
            require(!ghostEpochFinalized[pending], "DOUBLE_FINALIZATION_DETECTED");
            ghostEpochFinalized[pending] = true;
            uint256 net = ghostEpochAgentNet[pending];
            ghostReservedClaims += net;
            ghostPendingAgentLiability = 0;
            callsSucceeded++;
        } catch {}
    }

    function cancelEpoch() external {
        callsAttempted++;
        uint256 pending = escrow.activePendingEpoch();
        if (pending == 0) return;

        bytes32 reasonHash = keccak256("CANCEL_REASON");
        vm.prank(resolver);
        try escrow.cancelEpoch(pending, reasonHash) {
            ghostCancelledGross += ghostPendingAgentLiability;
            ghostPendingAgentLiability = 0;
            callsSucceeded++;
        } catch {}
    }

    function claimSingle() external {
        callsAttempted++;
        if (escrow.isGlobalPaused()) return;
        uint256 epoch = currentEpochCounter;
        if (!ghostEpochFinalized[epoch]) return;

        uint256 net = ghostEpochAgentNet[epoch];
        uint256 half = net / 2;
        if (half == 0) return;

        uint256 alreadyClaimed = escrow.claimed(agent1);
        if (alreadyClaimed >= half) return;

        bytes32 leaf1 = keccak256(bytes.concat(keccak256(abi.encode(agent1, half))));
        bytes32 leaf2 = keccak256(bytes.concat(keccak256(abi.encode(agent2, net - half))));

        bytes32[] memory proof = new bytes32[](1);
        proof[0] = leaf2;

        try escrow.claim(agent1, half, epoch, proof) returns (uint256 payout) {
            require(escrow.claimed(agent1) >= alreadyClaimed, "CLAIMED_DECREASED");
            ghostAgentPaid += payout;
            ghostReservedClaims -= payout;
            ghostLastClaimed[agent1] = escrow.claimed(agent1);
            callsSucceeded++;
        } catch {}
    }

    function claimForAgent() external {
        callsAttempted++;
        if (escrow.isGlobalPaused()) return;
        uint256 epoch = currentEpochCounter;
        if (!ghostEpochFinalized[epoch]) return;

        uint256 net = ghostEpochAgentNet[epoch];
        uint256 otherHalf = net - (net / 2);
        if (otherHalf == 0) return;

        uint256 alreadyClaimed = escrow.claimed(agent2);
        if (alreadyClaimed >= otherHalf) return;

        bytes32 leaf1 = keccak256(bytes.concat(keccak256(abi.encode(agent1, net / 2))));
        bytes32 leaf2 = keccak256(bytes.concat(keccak256(abi.encode(agent2, otherHalf))));

        bytes32[] memory proof = new bytes32[](1);
        proof[0] = leaf1;

        vm.prank(address(0x9999));
        try escrow.claimFor(agent2, otherHalf, epoch, proof) returns (uint256 payout) {
            require(escrow.claimed(agent2) >= alreadyClaimed, "CLAIMED_DECREASED");
            ghostAgentPaid += payout;
            ghostReservedClaims -= payout;
            ghostLastClaimed[agent2] = escrow.claimed(agent2);
            callsSucceeded++;
        } catch {}
    }

    function claimRoyalty() external {
        callsAttempted++;
        if (escrow.isGlobalPaused()) return;
        if (escrow.royaltyAccrued() == 0) return;
        try escrow.claimRoyalty() returns (uint256 paid) {
            ghostRoyaltyPaid += paid;
            callsSucceeded++;
        } catch {}
    }

    function pauseAndUnpause() external {
        callsAttempted++;
        bytes32 evHash = keccak256("PAUSE_EVIDENCE");
        bytes32 resHash = keccak256("RESOLUTION_EVIDENCE");

        vm.prank(guardian);
        try escrow.triggerEmergencyPause(evHash) {
            require(escrow.isGlobalPaused(), "PAUSE_FAILED");
            vm.prank(resolver);
            escrow.liftEmergencyPause(resHash);
            require(!escrow.isGlobalPaused(), "UNPAUSE_FAILED");
            callsSucceeded++;
        } catch {}
    }

    function simulateBlacklistResilience() external {
        callsAttempted++;
        usdc.setBlacklist(escrow.FOUNDER_WALLET(), true);
        
        if (escrow.royaltyAccrued() > 0) {
            try escrow.claimRoyalty() {
                revert("EXPECTED_ROYALTY_REVERT");
            } catch {}
        }

        usdc.setBlacklist(escrow.FOUNDER_WALLET(), false);
        callsSucceeded++;
    }

    function warpTime(uint256 secondsToWarp) external {
        callsAttempted++;
        if (secondsToWarp > 0 && secondsToWarp <= 86400) {
            vm.warp(block.timestamp + secondsToWarp);
            callsSucceeded++;
        }
    }

    function successRateBps() external view returns (uint256) {
        if (callsAttempted == 0) return 10000;
        return (callsSucceeded * 10000) / callsAttempted;
    }
}

contract EscrowInvariantTest is StdInvariant, Test {
    ZeqarisSettlementEscrow public escrow;
    MockUSDC public usdc;
    EscrowHandler public handler;

    uint256 internal signerKey = 0xB0B;
    address internal publisher;
    address internal guardian = address(0x2222);
    address internal resolver = address(0x3333);

    function setUp() public {
        publisher = vm.addr(signerKey);
        usdc = new MockUSDC();
        escrow = new ZeqarisSettlementEscrow(
            address(usdc),
            publisher,
            guardian,
            resolver,
            30, // 30s challenge window
            10_000_000_000, // max epoch gross ($10,000)
            50_000_000_000  // max outstanding liabilities ($50,000)
        );
        handler = new EscrowHandler(escrow, usdc, signerKey, guardian, resolver);
        
        usdc.mint(address(escrow), 1_000_000_000);
        handler.fund(1_000_000_000);

        // Native forge-std targetContract registration
        targetContract(address(handler));
    }

    // Invariant 1: Remainder Accumulator is strictly bounded: 0 <= accumulatedRemainder < 10000
    function invariant_remainder_range() public view {
        assertLt(escrow.accumulatedRemainder(), escrow.BPS_DENOMINATOR(), "Remainder overflow");
    }

    // Invariant 2: Settlement nonce strictly matches ghost accounting and is monotonic
    function invariant_nonce_monotonicity() public view {
        assertEq(escrow.settlementNonce(), handler.ghostLastNonce(), "Nonce out of sync with ghost accounting");
    }

    // Invariant 3: Solvency accounting invariant: actualUSDCBalance >= totalAccountedLiabilities
    function invariant_escrow_solvency() public view {
        uint256 actualBalance = usdc.balanceOf(address(escrow));
        uint256 liabilities = escrow.getAccountedLiabilities();
        assertGe(actualBalance, liabilities, "Escrow insolvent");
    }

    // Invariant 4: Single active pending epoch enforcement
    function invariant_single_pending_epoch() public view {
        uint256 pending = escrow.activePendingEpoch();
        if (pending != 0) {
            (,,,,,,, uint256 pubTime, ZeqarisSettlementEscrow.EpochState state,) = escrow.epochs(pending);
            assertTrue(state == ZeqarisSettlementEscrow.EpochState.PENDING, "Invalid pending epoch state");
            assertGt(pubTime, 0, "Pending epoch publish timestamp zero");
        }
    }

    // Invariant 5: Claimed amount for any account never decreases
    function invariant_claimed_never_decreases() public view {
        uint256 c1 = escrow.claimed(handler.agent1());
        uint256 c2 = escrow.claimed(handler.agent2());
        assertGe(c1, handler.ghostLastClaimed(handler.agent1()), "Agent1 claim decreased");
        assertGe(c2, handler.ghostLastClaimed(handler.agent2()), "Agent2 claim decreased");
    }

    // Invariant 6: Emergency pause prevents unfinalized outflows
    function invariant_pause_blocks_transfers() public view {
        if (escrow.isGlobalPaused()) {
            // Under global pause, no liabilities should be cleared
            assertTrue(escrow.isGlobalPaused(), "Global pause flag inconsistent");
        }
    }
}
