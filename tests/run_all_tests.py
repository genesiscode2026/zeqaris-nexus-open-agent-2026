"""Test runner for VELQIRIS Open Agent 2026."""

import unittest
import sys
import os

# Ensure agent package is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def run():
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.dirname(__file__), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    print("\n================================================================================")
    print("  VELQIRIS OPEN AGENT 2026 — LOCAL VERIFICATION SCORECARD")
    print("================================================================================")
    print(f"  Total Tests Executed:   {result.testsRun}")
    print(f"  Failures:               {len(result.failures)}")
    print(f"  Errors:                 {len(result.errors)}")
    status = "ALL TESTS PASSED (100% GREEN)" if result.wasSuccessful() else "TESTS FAILED"
    print(f"  Final Verdict:          {status}")
    print("================================================================================\n")
    
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    sys.exit(run())
