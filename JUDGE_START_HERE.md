# Judge start here — VELQIRIS

VELQIRIS is an evidence-first agent for Track 02. The shortest verification path is:

```bash
python3 tests/run_all_tests.py
```

Expected: **30/30 PASS**.

Then inspect:

1. `evidence/zetaris-platform-verification.json` — official Zetaris verifier, 9/9.
2. `evidence/zetaris-live-receipt.json` — two live SQL executions and MAD result.
3. `evidence/meterless-hmem-live-receipt.json` — official H-MEM runtime trace.
4. `evidence/meterless-hmem-conformance.json` — official suite, 13/13.
5. `PREEXISTING_TECHNOLOGY.md` — complete build-window disclosure.

The four market rows and their venue telemetry are declared synthetic values joined and executed by live Zetaris. They are intentionally deterministic for judging and do not represent independently onboarded external sources or production exchange feeds. No external model output, provider-cost claim, latency benchmark, or digital signature is asserted.
