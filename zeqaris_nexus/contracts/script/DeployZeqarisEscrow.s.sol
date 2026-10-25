// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "forge-std/Script.sol";
import "../src/ZeqarisSettlementEscrow.sol";

contract DeployZeqarisEscrow is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("DEPLOYER_PRIVATE_KEY");
        address usdcAddress = vm.envAddress("USDC_ADDRESS");
        address rootPublisher = vm.envAddress("ROOT_PUBLISHER_ADDRESS");
        address guardian = vm.envAddress("GUARDIAN_ADDRESS");
        address resolver = vm.envAddress("RESOLVER_ADDRESS");

        uint256 challengeWindow = vm.envOr("CHALLENGE_WINDOW", uint256(86400));
        uint256 maxEpochGross = vm.envOr("MAX_EPOCH_GROSS", uint256(10_000_000_000)); // $10,000 USDC (6 decimals)
        uint256 maxLiabilities = vm.envOr("MAX_LIABILITIES", uint256(50_000_000_000)); // $50,000 USDC (6 decimals)

        vm.startBroadcast(deployerPrivateKey);

        ZeqarisSettlementEscrow escrow = new ZeqarisSettlementEscrow(
            usdcAddress,
            rootPublisher,
            guardian,
            resolver,
            challengeWindow,
            maxEpochGross,
            maxLiabilities
        );

        vm.stopBroadcast();

        console.log("ZeqarisSettlementEscrow deployed at:", address(escrow));
    }
}
