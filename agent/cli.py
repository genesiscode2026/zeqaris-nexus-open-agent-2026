"""Command-line interface for running the VELQIRIS Open Agent."""

import argparse
import json
import sys
from pathlib import Path
try:
    from .config import AgentConfig
    from .evidence_explainer import EvidenceExplainer
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from agent.config import AgentConfig
    from agent.evidence_explainer import EvidenceExplainer

def main():
    parser = argparse.ArgumentParser(description="VELQIRIS Open Agent 2026 — The Agent That Can Explain Why")
    parser.add_argument("--query", default="SELECT * FROM market_feeds", help="SQL query to execute against Zetaris")
    parser.add_argument("--dry-run", action="store_true", help="Run in deterministic offline simulation mode")
    parser.add_argument("--output", default="market_truth_evidence_record.json", help="Path to write the evidence record")
    args = parser.parse_args()

    config = AgentConfig()
    explainer = EvidenceExplainer(config)

    print("================================================================================")
    print("  VELQIRIS OPEN AGENT 2026 — THE AGENT THAT CAN EXPLAIN WHY")
    print("  Track 02: The Agent That Can Explain Why")
    print("================================================================================\n")

    print(f"[*] Validating Data Layer (Zetaris)...")
    data_val = config.validate_data_layer()
    print(f"    - URL: {data_val['details']['rest_url']}")
    print(f"    - Org ID: {data_val['details']['org_id']}")
    print(f"    - API Key Configured: {data_val['details']['api_key_configured']}")
    print(f"    - Local Session Configured: {data_val['details']['local_session_configured']}")

    print(f"\n[*] Validating optional model adapter...")
    power_val = config.validate_power_layer()
    print(f"    - Model: {power_val['details']['model']}")
    print(f"    - Base URL: {power_val['details']['base_url']}")
    print(f"    - API Key Configured: {power_val['details']['api_key_configured']}")

    if not args.dry_run and (not data_val["ready"] or not power_val["ready"]):
        print("\n[FAIL] Live mode is not configured. Supply valid Zetaris and model credentials")
        print("       or rerun with --dry-run for an explicitly labelled fixture simulation.\n")
        return 2

    print(f"\n[*] Executing Evidence Investigation on query: '{args.query}'...")
    result = explainer.generate_evidence_investigation(query=args.query, dry_run=args.dry_run)
    if not result.get("success"):
        print(f"\n[FAIL] Investigation stopped at {result.get('stage')}: {result.get('error')}\n")
        return 1

    print("\n--------------------------------------------------------------------------------")
    print("  MATHEMATICAL CONSENSUS (MAD FILTERING)")
    print("--------------------------------------------------------------------------------")
    c = result["consensus"]
    print(f"  - Consensus VWAP:          ${c['consensus_vwap']:,.2f}")
    print(f"  - Median Price:            ${c['median_price']:,.2f}")
    print(f"  - Risk Regime:             {c['risk_regime']}")
    print(f"  - Inter-Venue Spread:      {c['spread_bps']} bps")
    print(f"  - Included Venues:         {[v['venue'] for v in c['included_venues']]}")
    print(f"  - Rejected Outliers:       {[v['venue'] for v in c['rejected_outliers']]}")

    print("\n--------------------------------------------------------------------------------")
    output_label = "OFFLINE SIMULATION OUTPUT" if args.dry_run else "LIVE MODEL OUTPUT"
    print(f"  {output_label}")
    print("--------------------------------------------------------------------------------")
    print(result["model_output"])

    print("\n--------------------------------------------------------------------------------")
    print("  EVIDENCE AUDIT RECORD")
    print("--------------------------------------------------------------------------------")
    print(f"  - SHA-256 Integrity Hash:  {result['evidence_hash']}")
    hmem = result["proof_record"]["meterless_hmem"]
    print(f"  - Meterless Engine:        {hmem['engine']}")
    print(f"  - H-MEM Ledger Head:       {hmem['trust_ledger_head_sha256']}")
    print(f"  - Local Cost Estimate:     ${result['meterless_cost']:.6f} USD")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result["proof_record"], f, indent=2)
    print(f"  - Proof Record Saved To:   {args.output}")
    print("\n[+] Investigation completed successfully.\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
