"""
Unit & Invariant Tests for Remainder Accumulator Engine
"""

import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.remainder_accumulator import RemainderAccumulatorEngine


class TestRemainderAccumulator(unittest.TestCase):

    def test_basic_micro_usdc_conservation(self):
        engine = RemainderAccumulatorEngine()
        
        # Epoch 1: 15 micro-USDC ($0.000015)
        # 15 * 500 = 7500. Royalty payout = 0, remainder carried = 7500
        rec1 = engine.process_epoch(1, 15)
        self.assertEqual(rec1.royalty_payout, 0)
        self.assertEqual(rec1.declared_agent_net, 15)
        self.assertEqual(rec1.carried_remainder, 7500)
        self.assertEqual(rec1.declared_agent_net + rec1.royalty_payout, 15)

        # Epoch 2: 25 micro-USDC ($0.000025)
        # 25 * 500 + 7500 = 20000. Royalty payout = 2, remainder carried = 0
        rec2 = engine.process_epoch(2, 25)
        self.assertEqual(rec2.royalty_payout, 2)
        self.assertEqual(rec2.declared_agent_net, 23)
        self.assertEqual(rec2.carried_remainder, 0)
        self.assertEqual(rec2.declared_agent_net + rec2.royalty_payout, 25)

        # Invariant over both epochs:
        # Total gross = 40. 5% of 40 = 2.
        self.assertEqual(engine.cumulative_gross, 40)
        self.assertEqual(engine.cumulative_royalty, 2)

    def test_property_based_conservation_fuzzing(self):
        engine = RemainderAccumulatorEngine()
        import random
        random.seed(42)

        total_gross = 0
        for epoch in range(1, 501):
            gross = random.randint(1, 10_000_000) # up to $10 USDC
            rec = engine.process_epoch(epoch, gross)
            total_gross += gross

            # Absolute conservation invariant on every step
            self.assertEqual(rec.declared_agent_net + rec.royalty_payout, gross)

        # Expected cumulative royalty: floor(total_gross * 0.05)
        # Remainder must be <= total_gross * 500 % 10000
        expected_cumulative_royalty = (total_gross * 500) // 10000
        self.assertEqual(engine.cumulative_royalty, expected_cumulative_royalty)


if __name__ == "__main__":
    unittest.main()
