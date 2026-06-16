"""
Agentic service layer. Owns the logic;

generate() runs the agentic workflow for one EvidenceExtraction and stores an
Evidence row. It is idempotent: the same source data + protocol version returns the
existing row instead of regenerating).
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings

from agentic.orchestrator import build_guides, run_intervention
from agentic.protocol import PROTOCOL_VERSION
from app.models import Evidence


class EvidenceService:
    @staticmethod
    def _ref_and_kind(extraction):
        p = getattr(extraction, "proposal", None)
        ref = getattr(p, "reference_number", None) or str(getattr(extraction, "pk", ""))
        kind = "program" if getattr(extraction, "national_proposal_id", None) else "intervention"
        return ref, kind

    @staticmethod
    def _store(ref, kind, merged, user=None):
        return Evidence.objects.create(
            intervention_ref=ref,
            proposal_kind=kind,
            data=merged["data"],
            dropped=merged["dropped"],
            flags=merged["flags"],
            reasoning=merged["reasoning"],
            protocol_version=PROTOCOL_VERSION,
            created_by=user if (user and user.is_authenticated) else None,
        )

    @staticmethod
    def generate_with_status(extraction, user=None):
        """Returns (evidence, status). status is always 'generated' now — no cache.
        Raises only when the whole extraction failed, so the caller can report why."""
        ref, kind = EvidenceService._ref_and_kind(extraction)
        guides = build_guides(extraction)

        merged = run_intervention(extraction.data or {}, guides)
        if merged["status"] == "failed":
            detail = "; ".join(f"{e['criterion']}: {e['error']}" for e in merged["errors"])
            raise RuntimeError(f"Extraction failed — {detail}")

        return EvidenceService._store(ref, kind, merged, user), "generated"

    @staticmethod
    def generate(extraction, user=None):
        evidence, _ = EvidenceService.generate_with_status(extraction, user=user)
        return evidence

    @staticmethod
    def generate_all(user=None, max_workers=None):
        from app.models import EvidenceExtraction

        workers = max(1, max_workers or getattr(settings, "GEMINI_WORKERS", 10))

        # 1) resolve inputs (sequential, DB reads only)
        pending = []
        for ext in EvidenceExtraction.objects.all().iterator():
            ref, kind = EvidenceService._ref_and_kind(ext)
            pending.append({
                "ref": ref,
                "kind": kind,
                "data": ext.data or {},
                "guides": build_guides(ext),
            })

        # 2) parallel phase: one worker per intervention. each does network only — no DB —
        #    so there are no per-thread connections. as soon as a worker finishes one
        #    intervention the pool hands it the next, until all are done.
        merged_by_index = {}
        if pending:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_map = {
                    pool.submit(run_intervention, p["data"], p["guides"]): i
                    for i, p in enumerate(pending)
                }
                for fut in as_completed(future_map):
                    merged_by_index[future_map[fut]] = fut.result()

        # 3) write phase: sequential on the main thread
        generated, failed = 0, []
        for i, p in enumerate(pending):
            merged = merged_by_index[i]
            if merged["status"] == "failed":
                detail = "; ".join(f"{e['criterion']}: {e['error']}" for e in merged["errors"])
                failed.append({"ref": p["ref"], "error": detail})
                continue  # not stored -> retries on the next run once fixed
            EvidenceService._store(p["ref"], p["kind"], merged, user)
            generated += 1

        return {
            "total": generated + len(failed),
            "generated": generated,
            "failed": failed,
        }