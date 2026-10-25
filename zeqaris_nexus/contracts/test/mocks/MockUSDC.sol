// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import "../../src/ZeqarisSettlementEscrow.sol";

contract MockUSDC is IERC20 {
    string public name = "USD Coin";
    string public symbol = "USDC";
    uint8 public decimals = 6;

    uint256 public override totalSupply;
    mapping(address => uint256) public override balanceOf;
    mapping(address => mapping(address => uint256)) public override allowance;
    mapping(address => bool) public blacklisted;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        totalSupply += amount;
    }

    function setBlacklist(address account, bool isBlacklisted) external {
        blacklisted[account] = isBlacklisted;
    }

    function transfer(address to, uint256 value) external override returns (bool) {
        require(!blacklisted[msg.sender], "MockUSDC: SENDER_BLACKLISTED");
        require(!blacklisted[to], "MockUSDC: RECIPIENT_BLACKLISTED");
        require(balanceOf[msg.sender] >= value, "MockUSDC: INSUFFICIENT_BALANCE");
        balanceOf[msg.sender] -= value;
        balanceOf[to] += value;
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external override returns (bool) {
        require(!blacklisted[from], "MockUSDC: FROM_BLACKLISTED");
        require(!blacklisted[to], "MockUSDC: TO_BLACKLISTED");
        require(balanceOf[from] >= value, "MockUSDC: INSUFFICIENT_BALANCE");
        if (allowance[from][msg.sender] != type(uint256).max) {
            require(allowance[from][msg.sender] >= value, "MockUSDC: INSUFFICIENT_ALLOWANCE");
            allowance[from][msg.sender] -= value;
        }
        balanceOf[from] -= value;
        balanceOf[to] += value;
        return true;
    }
}
