/**
 * Execute a VELQIRIS evidence-memory cycle through Meterless's official H-MEM
 * reference implementation and emit a redaction-safe receipt.
 *
 * Usage:
 *   npx tsx scripts/meterless_official_bridge.ts input.json receipt.json persist-dir
 */

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { HMEM } from "../vendor/meterless-hmem-reference/src/index.ts";

type BridgeInput = {
  runId: string;
  query: string;
  memories: Array<{
    content: string;
    source: string;
    type?: "personal" | "factual" | "preference" | "general";
    layer?: "short_term" | "working" | "long_term";
    confidence?: number;
    tags?: string[];
    derivedFrom?: string[];
  }>;
};

const [, , inputArg, outputArg, persistArg] = process.argv;
if (!inputArg || !outputArg || !persistArg) {
  throw new Error("Expected input JSON, output receipt, and persistence directory.");
}

const inputPath = path.resolve(inputArg);
const outputPath = path.resolve(outputArg);
const persistDir = path.resolve(persistArg);
const payload = JSON.parse(fs.readFileSync(inputPath, "utf-8")) as BridgeInput;

if (!payload.runId || !payload.query || !Array.isArray(payload.memories) || payload.memories.length === 0) {
  throw new Error("Invalid bridge input: runId, query, and at least one memory are required.");
}

fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.mkdirSync(persistDir, { recursive: true });

const hmem = new HMEM({ actor: "velqiris-open-agent", persistDir });
const stored = payload.memories.map((memory) => hmem.add({
  content: memory.content,
  source: memory.source,
  type: memory.type ?? "factual",
  layer: memory.layer ?? "working",
  confidence: memory.confidence ?? 1.0,
  tags: memory.tags ?? [],
  derivedFrom: memory.derivedFrom,
}));

const retrieval = hmem.query(payload.query, { topN: 5, threshold: 0 });
const ledger = hmem.ledger.all();
const ledgerDigest = crypto
  .createHash("sha256")
  .update(JSON.stringify(ledger))
  .digest("hex");

const receipt = {
  schema_version: "1.0",
  run_id: payload.runId,
  engine: "Meterless H-MEM official reference",
  engine_package: "@meterless/hmem-reference",
  engine_version: "0.1.0",
  upstream_repository: "https://github.com/Meterless/Meterless",
  upstream_commit: "1742dec56a66e58eef9dda2d2b865823758ca8cd",
  storage_mode: "LOCAL_PERSISTENT",
  stored_memory_ids: stored.map((memory) => memory.id),
  retrieved_memory_ids: retrieval.memories.map((item) => item.memory.id),
  retrieval_strategy: retrieval.trace.strategy,
  retrieval_reason: retrieval.trace.retrievalReason,
  retrieval_scores: retrieval.trace.scores,
  trust_ledger_entries: ledger.length,
  trust_ledger_sha256: ledgerDigest,
  persisted_files: ["state.json", "ledger.jsonl"],
  conformance_suite: "vendor/meterless-hmem-conformance/runner.ts",
  redaction_note: "No credentials, bearer tokens, passwords, or private account identifiers are included.",
};

fs.writeFileSync(outputPath, JSON.stringify(receipt, null, 2) + "\n", "utf-8");
console.log(`Meterless H-MEM receipt written: ${outputPath}`);
