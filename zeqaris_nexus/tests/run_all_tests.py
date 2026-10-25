#!/usr/bin/env python3
"""
Test Runner for ZEQARIS NEXUS Verification Suite
"""

import sys
import unittest
from pathlib import Path

def run():
    loader = unittest.TestLoader()
    test_dir = Path(__file__).resolve().parent
    suite = loader.discover(str(test_dir), pattern="test_*.py", top_level_dir=str(test_dir.parent))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        sys.exit(1)

if __name__ == "__main__":
    run()
