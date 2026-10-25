"""Meterless H-MEM core integration for VELQIRIS.

This module implements the H-MEM contract used by this submission: canonical
memories with lineage, hierarchical layers, hybrid retrieval, explicit trace
metadata, and an append-only hash-chained trust ledger.  H-MEM is an
implementation specification rather than a hosted API, so the integration is
local-first and has no credential requirement.

Official specification:
https://github.com/Meterless/Meterless/tree/main/engines/hmem
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional


SPEC_URL = "https://github.com/Meterless/Meterless/tree/main/engines/hmem"
IMPLEMENTATION_PROFILE = "hmem-core-capture-retrieval-trust-ledger"
_LAYERS = {"short_term", "working", "long_term"}
_TYPES = {"personal", "factual", "preference", "general"}
_LAYER_WEIGHT = {"short_term": 0.02, "working": 0.05, "long_term": 0.08}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_]+", value.lower())
        if len(token) > 1
    }


@dataclass
class MemoryRecord:
    """Canonical H-MEM memory record with provenance and graph fields."""

    id: str
    content: str
    type: str
    layer: str
    timestamp: str
    lastAccessed: str
    accessCount: int
    tags: List[str]
    confidence: float
    source: str
    domain: str
    namespace: str
    entities: List[Dict[str, str]] = field(default_factory=list)
    relatedTo: List[str] = field(default_factory=list)
    supersedes: Optional[str] = None
    derivedFrom: List[str] = field(default_factory=list)


class MeterlessHMem:
    """Small, dependency-free H-MEM implementation for the agent workflow."""

    def __init__(self, storage_dir: Optional[str] = None):
        self.memories: Dict[str, MemoryRecord] = {}
        self.ledger: List[Dict[str, Any]] = []
        self.storage_dir = Path(storage_dir).expanduser() if storage_dir else None
        if self.storage_dir:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            self._load()

    def add_memory(
        self,
        content: str,
        *,
        source: str,
        memory_type: str = "factual",
        layer: str = "working",
        tags: Optional[Iterable[str]] = None,
        confidence: float = 1.0,
        domain: str = "market_integrity",
        namespace: str = "velqiris/evidence",
        entities: Optional[Iterable[Dict[str, str]]] = None,
        related_to: Optional[Iterable[str]] = None,
        supersedes: Optional[str] = None,
        derived_from: Optional[Iterable[str]] = None,
        actor: str = "velqiris-agent",
    ) -> MemoryRecord:
        """Store a provenance-bearing memory and audit the mutation."""
        if not content.strip():
            raise ValueError("H-MEM memory content must not be empty.")
        if not source.strip():
            raise ValueError("H-MEM requires a non-empty provenance source.")
        if layer not in _LAYERS:
            raise ValueError(f"Unsupported H-MEM layer: {layer}")
        if memory_type not in _TYPES:
            raise ValueError(f"Unsupported H-MEM memory type: {memory_type}")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("H-MEM confidence must be between 0 and 1.")

        now = _utc_now()
        record = MemoryRecord(
            id=str(uuid.uuid4()),
            content=content.strip(),
            type=memory_type,
            layer=layer,
            timestamp=now,
            lastAccessed=now,
            accessCount=0,
            tags=sorted(set(tags or [])),
            confidence=confidence,
            source=source.strip(),
            domain=domain,
            namespace=namespace,
            entities=list(entities or [])[:10],
            relatedTo=list(related_to or [])[:5],
            supersedes=supersedes,
            derivedFrom=list(derived_from or []),
        )
        self.memories[record.id] = record
        self._append_ledger(
            memory_id=record.id,
            action="create",
            actor=actor,
            details={
                "source": record.source,
                "layer": record.layer,
                "confidence": record.confidence,
            },
            new_state=asdict(record),
        )
        self._persist()
        return record

    def retrieve(
        self,
        query: str,
        *,
        top_n: int = 5,
        threshold: float = 0.10,
        domain: Optional[str] = None,
        tags: Optional[Iterable[str]] = None,
        entities: Optional[Iterable[str]] = None,
        actor: str = "velqiris-agent",
    ) -> Dict[str, Any]:
        """Retrieve context using H-MEM-style multi-signal hybrid ranking."""
        query_tokens = _tokens(query)
        query_tags = set(tags or [])
        query_entities = {value.lower() for value in (entities or [])}
        ranked: List[Dict[str, Any]] = []

        for record in self.memories.values():
            content_tokens = _tokens(record.content)
            overlap = len(query_tokens & content_tokens) / max(len(query_tokens), 1)
            tag_overlap = len(query_tags & set(record.tags)) / max(len(query_tags), 1) if query_tags else 0.0
            record_entities = {
                str(entity.get("name", "")).lower() for entity in record.entities
            }
            entity_overlap = len(query_entities & record_entities) / max(len(query_entities), 1) if query_entities else 0.0
            domain_boost = 0.15 if domain and record.domain == domain else 0.0
            recency_hours = max(
                (time.time() - datetime.fromisoformat(record.timestamp).timestamp()) / 3600.0,
                0.0,
            )
            recency_boost = max(0.0, 0.08 - min(recency_hours / 24.0, 1.0) * 0.08)
            superseded_penalty = 0.20 if any(
                candidate.supersedes == record.id for candidate in self.memories.values()
            ) else 0.0
            score = (
                0.50 * overlap
                + 0.10 * tag_overlap
                + 0.10 * entity_overlap
                + domain_boost
                + _LAYER_WEIGHT[record.layer]
                + recency_boost
                + 0.10 * record.confidence
                - superseded_penalty
            )
            if score >= threshold:
                ranked.append(
                    {
                        "memory": record,
                        "score": round(score, 6),
                        "retrievalReason": {
                            "keyword_overlap": round(overlap, 6),
                            "tag_overlap": round(tag_overlap, 6),
                            "entity_overlap": round(entity_overlap, 6),
                            "domain_match": bool(domain and record.domain == domain),
                            "layer": record.layer,
                            "confidence": record.confidence,
                        },
                    }
                )

        ranked.sort(key=lambda item: (item["score"], item["memory"].timestamp), reverse=True)
        selected = ranked[: max(top_n, 0)]
        for item in selected:
            record = item["memory"]
            previous = {"lastAccessed": record.lastAccessed, "accessCount": record.accessCount}
            record.lastAccessed = _utc_now()
            record.accessCount += 1
            self._append_ledger(
                memory_id=record.id,
                action="read",
                actor=actor,
                details={"query": query, "score": item["score"]},
                previous_state=previous,
                new_state={"lastAccessed": record.lastAccessed, "accessCount": record.accessCount},
            )
        self._persist()

        trace = [
            {
                "memoryId": item["memory"].id,
                "content": item["memory"].content,
                "source": item["memory"].source,
                "domain": item["memory"].domain,
                "layer": item["memory"].layer,
                "score": item["score"],
                "retrievalReason": item["retrievalReason"],
            }
            for item in selected
        ]
        context = "\n".join(
            f"[{item['layer']} | {item['domain']} | source={item['source']}] {item['content']}"
            for item in trace
        )
        return {
            "strategy": "comprehensive" if top_n > 3 else "minimal",
            "query": query,
            "threshold": threshold,
            "context": context,
            "trace": trace,
        }

    def receipt(self, *, stored_ids: Iterable[str], retrieval: Dict[str, Any]) -> Dict[str, Any]:
        """Return a redaction-safe execution receipt for the evidence record."""
        return {
            "engine": "Meterless H-MEM",
            "implementation_profile": IMPLEMENTATION_PROFILE,
            "specification": SPEC_URL,
            "storage_mode": "LOCAL_PERSISTENT" if self.storage_dir else "LOCAL_IN_MEMORY",
            "stored_memory_ids": list(stored_ids),
            "retrieved_memory_ids": [item["memoryId"] for item in retrieval.get("trace", [])],
            "retrieval_strategy": retrieval.get("strategy"),
            "retrieval_threshold": retrieval.get("threshold"),
            "trust_ledger_entries": len(self.ledger),
            "trust_ledger_head_sha256": self.ledger[-1]["entryHash"] if self.ledger else None,
            "scope_note": (
                "Implements H-MEM canonical records, tiered layers, hybrid retrieval, "
                "trace metadata and an append-only trust ledger. Dreaming, sleep and "
                "conflict-resolution services are outside this hackathon profile."
            ),
        }

    def verify_ledger(self) -> bool:
        """Verify the complete hash chain without trusting stored entry hashes."""
        previous_hash: Optional[str] = None
        for entry in self.ledger:
            payload = {key: value for key, value in entry.items() if key != "entryHash"}
            if payload.get("previousHash") != previous_hash:
                return False
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            if digest != entry.get("entryHash"):
                return False
            previous_hash = digest
        return True

    def _append_ledger(
        self,
        *,
        memory_id: str,
        action: str,
        actor: str,
        details: Dict[str, Any],
        previous_state: Optional[Dict[str, Any]] = None,
        new_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "memoryId": memory_id,
            "action": action,
            "actor": actor,
            "timestamp": _utc_now(),
            "previousHash": self.ledger[-1]["entryHash"] if self.ledger else None,
            "previousState": previous_state,
            "newState": new_state,
            "details": details,
        }
        payload["entryHash"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.ledger.append(payload)

    def _persist(self) -> None:
        if not self.storage_dir:
            return
        memories_path = self.storage_dir / "memories.json"
        ledger_path = self.storage_dir / "trust-ledger.jsonl"
        memories_path.write_text(
            json.dumps([asdict(item) for item in self.memories.values()], indent=2, sort_keys=True),
            encoding="utf-8",
        )
        ledger_path.write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in self.ledger),
            encoding="utf-8",
        )

    def _load(self) -> None:
        if not self.storage_dir:
            return
        memories_path = self.storage_dir / "memories.json"
        ledger_path = self.storage_dir / "trust-ledger.jsonl"
        if memories_path.exists():
            for item in json.loads(memories_path.read_text(encoding="utf-8")):
                record = MemoryRecord(**item)
                self.memories[record.id] = record
        if ledger_path.exists():
            self.ledger = [
                json.loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if not self.verify_ledger():
                raise ValueError("H-MEM trust ledger verification failed.")
