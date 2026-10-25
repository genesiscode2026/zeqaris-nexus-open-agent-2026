// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "forge-std/Test.sol";
import "../../src/ZeqarisSettlementEscrow.sol";
import "../mocks/MockUSDC.sol";

contract ZeqarisSettlementEscrowUnitTest is Test {
    ZeqarisSettlementEscrow public escrow;
    MockUSDC public usdc;

    uint256 internal signerPrivateKey = 0xA11CE;
    address internal publisher;
    address internal guardian = address(0x2222);
    address internal resolver = address(0x3333);
    address internal agent1 = address(0x4444);
    address internal admin;

    bytes32 internal policyHash = keccak256("ZEQARIS/POLICY/V1");

    function setUp() public {
        publisher = vm.addr(signerPrivateKey);
        usdc = new MockUSDC();

        escrow = new ZeqarisSettlementEscrow(
            address(usdc),
            publisher,
            guardian,
            resolver,
            30, // 30 seconds challenge window
            10_000_000_000, // $10,000 max single epoch
            50_000_000_000  // $50,000 max outstanding liabilities
        );

        admin = escrow.admin();

        // Fund escrow with 100 USDC ($100 = 100_000_000 micro-USDC)
        usdc.mint(address(escrow), 100_000_000);
    }

    function test_voucher_settlement_and_remainder() public {
        bytes32 leaf1 = keccak256(bytes.concat(keccak256(abi.encode(agent1, uint256(15)))));
        bytes32 root = leaf1; // 1-leaf Merkle tree

        ZeqarisSettlementEscrow.SettlementVoucher memory voucher = ZeqarisSettlementEscrow.SettlementVoucher({
            settlementNonce: 1,
            epoch: 1,
            checkpointRoot: keccak256("checkpoint-1"),
            merkleRoot: root,
            grossAmount: 15,
            agentNetTotal: 15,
            royaltyAmount: 0,
            remainderBefore: 0,
            remainderAfter: 7500,
            validAfter: uint48(block.timestamp),
            deadline: uint48(block.timestamp + 3600),
            policyHash: policyHash
        });

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
        bytes memory sig = abi.encodePacked(r, s, v);

        // Submit voucher
        escrow.submitSettlementVoucher(voucher, sig);
        require(escrow.accumulatedRemainder() == 0, "Remainder should not mutate at submit");
        require(escrow.royaltyAccrued() == 0, "Royalty should not accrue at submit");

        // Warp past challenge window
        vm.warp(block.timestamp + 31);
        escrow.finalizeEpoch(1);

        require(escrow.accumulatedRemainder() == 7500, "Remainder mismatch after finalize");
        require(escrow.royaltyAccrued() == 0, "Royalty accrued mismatch");

        // Agent claims reward
        bytes32[] memory emptyProof = new bytes32[](0);
        uint256 payout = escrow.claim(agent1, 15, 1, emptyProof);
        require(payout == 15, "Payout mismatch");
        require(usdc.balanceOf(agent1) == 15, "Agent balance mismatch");
    }

    function test_royalty_pull_payment_liveness() public {
        ZeqarisSettlementEscrow.SettlementVoucher memory voucher = ZeqarisSettlementEscrow.SettlementVoucher({
            settlementNonce: 1,
            epoch: 1,
            checkpointRoot: keccak256("cp-1"),
            merkleRoot: keccak256("root-1"),
            grossAmount: 100_000,
            agentNetTotal: 95_000,
            royaltyAmount: 5_000,
            remainderBefore: 0,
            remainderAfter: 0,
            validAfter: uint48(block.timestamp),
            deadline: uint48(block.timestamp + 3600),
            policyHash: policyHash
        });

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
        bytes memory sig = abi.encodePacked(r, s, v);

        escrow.submitSettlementVoucher(voucher, sig);
        require(escrow.royaltyAccrued() == 0, "Should be zero before finalize");

        // Warp and finalize
        vm.warp(block.timestamp + 31);
        escrow.finalizeEpoch(1);
        require(escrow.royaltyAccrued() == 5_000, "Accrual failed after finalize");

        // Pull royalty
        uint256 pulled = escrow.claimRoyalty();
        require(pulled == 5_000, "Pulled amount mismatch");
        require(usdc.balanceOf(escrow.FOUNDER_WALLET()) == 5_000, "Founder wallet balance mismatch");
        require(escrow.royaltyAccrued() == 0, "Accrued should reset");
    }

    function test_reject_zero_epoch() public {
        ZeqarisSettlementEscrow.SettlementVoucher memory voucher = ZeqarisSettlementEscrow.SettlementVoucher({
            settlementNonce: 1,
            epoch: 0, // FORBIDDEN ZERO EPOCH
            checkpointRoot: keccak256("cp-0"),
            merkleRoot: keccak256("root-0"),
            grossAmount: 10_000,
            agentNetTotal: 9_500,
            royaltyAmount: 500,
            remainderBefore: 0,
            remainderAfter: 0,
            validAfter: uint48(block.timestamp),
            deadline: uint48(block.timestamp + 3600),
            policyHash: policyHash
        });

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
        bytes memory sig = abi.encodePacked(r, s, v);

        vm.expectRevert(bytes("ZEQARIS: ZERO_EPOCH_RESERVED"));
        escrow.submitSettlementVoucher(voucher, sig);
    }

    function test_cancel_epoch() public {
        ZeqarisSettlementEscrow.SettlementVoucher memory voucher = ZeqarisSettlementEscrow.SettlementVoucher({
            settlementNonce: 1,
            epoch: 1,
            checkpointRoot: keccak256("cp-1"),
            merkleRoot: keccak256("root-1"),
            grossAmount: 10_000,
            agentNetTotal: 9_500,
            royaltyAmount: 500,
            remainderBefore: 0,
            remainderAfter: 0,
            validAfter: uint48(block.timestamp),
            deadline: uint48(block.timestamp + 3600),
            policyHash: policyHash
        });

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
        bytes memory sig = abi.encodePacked(r, s, v);

        escrow.submitSettlementVoucher(voucher, sig);
        require(escrow.activePendingEpoch() == 1, "Should be active pending");

        // Resolver cancels pending epoch
        bytes32 reasonHash = keccak256("CANCEL_REASON");
        vm.prank(resolver);
        escrow.cancelEpoch(1, reasonHash);

        require(escrow.activePendingEpoch() == 0, "Active pending should be reset to 0");
        require(escrow.royaltyAccrued() == 0, "Royalty should remain 0");
        require(escrow.accumulatedRemainder() == 0, "Remainder should remain 0");
    }

    function test_emergency_pause_and_unpause() public {
        bytes32 evHash = keccak256("PAUSE_EVIDENCE");
        bytes32 resHash = keccak256("RESOLUTION_EVIDENCE");

        // Non-guardian cannot pause
        vm.prank(address(0x9999));
        vm.expectRevert(bytes("ZEQARIS: NOT_GUARDIAN"));
        escrow.triggerEmergencyPause(evHash);

        // Guardian pauses
        vm.prank(guardian);
        escrow.triggerEmergencyPause(evHash);
        require(escrow.isGlobalPaused(), "Should be paused");

        // While paused, claimRoyalty reverts with GLOBAL_PAUSED
        vm.expectRevert(bytes("ZEQARIS: GLOBAL_PAUSED"));
        escrow.claimRoyalty();

        // Guardian cannot unpause (least privilege)
        vm.prank(guardian);
        vm.expectRevert(bytes("ZEQARIS: NOT_RESOLVER"));
        escrow.liftEmergencyPause(resHash);

        // Resolver unpauses
        vm.prank(resolver);
        escrow.liftEmergencyPause(resHash);
        require(!escrow.isGlobalPaused(), "Should be unpaused");
    }

    function test_publisher_rotation_timelock() public {
        address newPub = address(0x8888);

        // Propose rotation (must be admin)
        vm.prank(admin);
        escrow.proposePublisherRotation(newPub);

        // Cannot execute before 1 day
        vm.prank(admin);
        vm.expectRevert(bytes("ZEQARIS: TIMELOCK_ACTIVE"));
        escrow.executePublisherRotation();

        // Warp 1 day + 1s
        vm.warp(block.timestamp + 1 days + 1);
        vm.prank(admin);
        escrow.executePublisherRotation();

        require(escrow.rootPublisher() == newPub, "Publisher should be rotated");
    }

    function test_reject_high_s() public {
        uint256 secp256k1_n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141;

        ZeqarisSettlementEscrow.SettlementVoucher memory voucher = ZeqarisSettlementEscrow.SettlementVoucher({
            settlementNonce: 1,
            epoch: 1,
            checkpointRoot: keccak256("cp-1"),
            merkleRoot: keccak256("root-1"),
            grossAmount: 10_000,
            agentNetTotal: 9_500,
            royaltyAmount: 500,
            remainderBefore: 0,
            remainderAfter: 0,
            validAfter: uint48(block.timestamp),
            deadline: uint48(block.timestamp + 3600),
            policyHash: policyHash
        });

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

        bytes32 high_s = bytes32(secp256k1_n - uint256(s));
        bytes memory sig = abi.encodePacked(r, high_s, v);

        vm.expectRevert(bytes("ZEQARIS: INVALID_SIG_S"));
        escrow.submitSettlementVoucher(voucher, sig);
    }

    function test_reject_wrong_signer() public {
        uint256 wrongKey = 0xBAD;

        ZeqarisSettlementEscrow.SettlementVoucher memory voucher = ZeqarisSettlementEscrow.SettlementVoucher({
            settlementNonce: 1,
            epoch: 1,
            checkpointRoot: keccak256("cp-1"),
            merkleRoot: keccak256("root-1"),
            grossAmount: 10_000,
            agentNetTotal: 9_500,
            royaltyAmount: 500,
            remainderBefore: 0,
            remainderAfter: 0,
            validAfter: uint48(block.timestamp),
            deadline: uint48(block.timestamp + 3600),
            policyHash: policyHash
        });

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
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(wrongKey, digest);
        bytes memory sig = abi.encodePacked(r, s, v);

        vm.expectRevert(bytes("ZEQARIS: INVALID_ICP_SIGNATURE"));
        escrow.submitSettlementVoucher(voucher, sig);
    }

    function test_reject_expired_voucher() public {
        ZeqarisSettlementEscrow.SettlementVoucher memory voucher = ZeqarisSettlementEscrow.SettlementVoucher({
            settlementNonce: 1,
            epoch: 1,
            checkpointRoot: keccak256("cp-1"),
            merkleRoot: keccak256("root-1"),
            grossAmount: 10_000,
            agentNetTotal: 9_500,
            royaltyAmount: 500,
            remainderBefore: 0,
            remainderAfter: 0,
            validAfter: uint48(block.timestamp),
            deadline: uint48(block.timestamp - 1), // EXPIRED
            policyHash: policyHash
        });

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
        bytes memory sig = abi.encodePacked(r, s, v);

        vm.expectRevert(bytes("ZEQARIS: VOUCHER_EXPIRED"));
        escrow.submitSettlementVoucher(voucher, sig);
    }
}
