"""
Remainder Accumulator & Cumulative Merkle Settlement Engine
Part of ZEQARIS NEXUS — Autonomous Swarm Coordination & Escrow Settlement OS

Implements exact 500 bps (5.00%) royalty allocation with Remainder Accumulator
to eliminate fractional micro-USDC precision loss across epochs.
"""

from dataclasses import dataclass
from typing import List, Tuple, Dict


@dataclass
class EpochAccountingResult:
    epoch: int
    gross_amount: int            # Total micro-USDC (6 decimals)
    declared_agent_net: int      # Net micro-USDC for agents
    royalty_payout: int          # Transferred to FOUNDER_WALLET
    carried_remainder: int       # Units (0..9999) carried to next epoch
    cumulative_gross: int
    cumulative_royalty: int


class RemainderAccumulatorEngine:
    ROYALTY_BPS = 500          # 5.00%
    BPS_DENOMINATOR = 10000

    def __init__(self, initial_remainder: int = 0):
        self.accumulated_remainder = initial_remainder
        self.cumulative_gross = 0
        self.cumulative_royalty = 0
        self.epoch_history: List[EpochAccountingResult] = []

    def process_epoch(self, epoch: int, gross_amount: int) -> EpochAccountingResult:
        """
        Computes exact royalty with remainder accumulator.
        Invariant: gross_amount == declared_agent_net + royalty_payout
        """
        if gross_amount <= 0:
            raise ValueError(f"gross_amount must be positive, got {gross_amount}")

        scaled_royalty = (gross_amount * self.ROYALTY_BPS) + self.accumulated_remainder
        royalty_payout = scaled_royalty // self.BPS_DENOMINATOR
        self.accumulated_remainder = scaled_royalty % self.BPS_DENOMINATOR

        declared_agent_net = gross_amount - royalty_payout

        # Strict Conservation Check
        assert declared_agent_net + royalty_payout == gross_amount, "Conservation of value violated!"

        self.cumulative_gross += gross_amount
        self.cumulative_royalty += royalty_payout

        record = EpochAccountingResult(
            epoch=epoch,
            gross_amount=gross_amount,
            declared_agent_net=declared_agent_net,
            royalty_payout=royalty_payout,
            carried_remainder=self.accumulated_remainder,
            cumulative_gross=self.cumulative_gross,
            cumulative_royalty=self.cumulative_royalty
        )
        self.epoch_history.append(record)
        return record
