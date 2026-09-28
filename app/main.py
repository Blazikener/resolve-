"""HTTP surface for the reviewer screen. Thin: every route calls one function in store/agent/policy."""
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from .models import Evidence
from . import store, agent, evaluation

app = FastAPI(title="Resolve demo")
STATIC = Path(__file__).resolve().parent.parent / "static"
_EVAL_CACHE: dict[str, dict] = {}


def get_case(case_id: str):
    case = store.CASES.get(case_id)
    if not case:
        raise HTTPException(404, "no such case")
    return case


@app.get("/")
def index():
    return FileResponse(STATIC / "story.html")


@app.get("/workspace")
def workspace():
    return FileResponse(STATIC / "index.html")


@app.get("/api/meta")
def meta():
    import os
    return {"rules_version": store.RULES_VERSION, "today": store.TODAY.isoformat(), "entities": store.ENTITY_NAMES,
            "owners": store.OWNERS, "llm_available": bool(os.environ.get("OPENAI_API_KEY")),
            "llm_model": os.environ.get("RESOLVE_MODEL", "gpt-4o-mini"), "max_tool_calls": agent.MAX_TOOL_CALLS,
            "tools": [t["name"] for t in agent.TOOL_SPECS]}


@app.get("/api/cases")
def list_cases():
    return [store.queue_summary(c) for c in store.CASES.values()]


@app.get("/api/cases/{case_id}")
def case_detail(case_id: str):
    c = get_case(case_id)
    return c.to_dict() | {"ageing_days": store.ageing_days(c), "owners": store.OWNERS[c.entity]}


@app.post("/api/cases/{case_id}/investigate")
def investigate(case_id: str, mode: str = Query("auto", pattern="^(auto|scripted|llm|redteam)$")):
    case = get_case(case_id)
    try:
        trace = agent.investigate(case, mode)
    except Exception as exc:  # model outage etc. -> case stays in manual review, visibly
        store.audit(case, "system", "investigate.error", f"planner failed: {type(exc).__name__}: {exc}"[:200])
        raise HTTPException(502, f"planner failed: {exc}")
    return {"trace": trace, "drafts": [d.__dict__ for d in case.drafts]}


class Decision(BaseModel):
    approve: bool


@app.post("/api/cases/{case_id}/drafts/{draft_id}")
def decide_draft(case_id: str, draft_id: str, body: Decision):
    case = get_case(case_id)
    draft = next((d for d in case.drafts if d.id == draft_id), None)
    if not draft:
        raise HTTPException(404, "no such draft")
    if draft.status == "approved":
        store.audit(case, "reviewer", "outbox.duplicate_suppressed", f"{draft.id} already approved (dedup {draft.dedup_key})")
        return draft.__dict__
    draft.status = "approved" if body.approve else "rejected"
    store.audit(case, "reviewer", f"draft.{draft.status}", f"{draft.id} -> {draft.recipient} (pilot: draft only, not sent)")
    return draft.__dict__


class SupplierEmail(BaseModel):
    text: str = "Hi, confirming the remaining boxes were delivered to the clinic last Thursday. Please release payment. Regards, Supplier"


@app.post("/api/cases/{case_id}/events/supplier-email")
def supplier_email(case_id: str, body: SupplierEmail):
    """An email is untrusted evidence. It is recorded, shown to the reviewer, and proves nothing."""
    case = get_case(case_id)
    n = len([e for e in case.evidence if e.kind == "email"]) + 1
    store.add_evidence(case, Evidence(id=f"EMAIL-{n}", kind="email", entity=case.entity, trust="untrusted", source="mailbox",
                                      summary=f'Supplier email: "{body.text[:160]}"', data={"text": body.text}))
    return case_detail(case_id)


class GrnPost(BaseModel):
    po_line: str
    qty: float
    grn_id: str = "GRN-95"
    entity: str | None = None      # allows the cross-entity demonstration


@app.post("/api/cases/{case_id}/events/grn")
def post_grn(case_id: str, body: GrnPost):
    """An authorised receiver posted a goods receipt in the ERP. Authoritative -> rules rerun."""
    case = get_case(case_id)
    entity = body.entity or case.entity
    n = len(store.erp(entity)["grns"]) + 1
    ev = store.erp_grn(entity, f"{body.grn_id}/L{n}", body.po_line, body.qty, store.TODAY.isoformat())
    store.add_evidence(case, ev)
    return case_detail(case_id)


class AmendmentPost(BaseModel):
    po_line: str
    unit_price: float
    approved_by: str = "procurement.manager"
    approved: bool = True


@app.post("/api/cases/{case_id}/events/amendment")
def post_amendment(case_id: str, body: AmendmentPost):
    case = get_case(case_id)
    n = len(store.erp(case.entity)["amendments"]) + 1
    ev = store.erp_amendment(case.entity, f"AMD-{n}", body.po_line, body.unit_price, body.approved_by)
    ev.data["approved"] = body.approved
    if not body.approved:
        ev.summary = ev.summary.replace("Approved amendment", "DRAFT amendment (not approved)")
    store.add_evidence(case, ev)
    return case_detail(case_id)


@app.post("/api/cases/{case_id}/events/reupload")
def reupload(case_id: str):
    """Same invoice arrives again (retry, second scan, duplicate feed). Must NOT create a second case."""
    case = get_case(case_id)
    lines = [{"po_line": e.data["po_line"], "qty": e.data["qty"], "unit_price": e.data["unit_price"]}
             for e in case.evidence if e.kind == "invoice_line"]
    result, created = store.ingest_invoice(case.entity, case.supplier, case.invoice_id, case.po_id, lines, source="re-upload")
    return {"created": created, "case_id": result.id, "cases_total": len(store.CASES)}


class IngestLine(BaseModel):
    po_line: str
    qty: float
    unit_price: float


class IngestBody(BaseModel):
    entity: str
    supplier: str
    invoice_id: str
    po_id: str
    lines: list[IngestLine]
    remarks: str = ""


@app.post("/api/ingest")
def ingest(body: IngestBody):
    """A new structured invoice arrives from the ASP/ERP feed. Records are linked by entity + PO line."""
    if body.entity not in store.OWNERS:
        raise HTTPException(400, "unknown legal entity")
    if not body.lines:
        raise HTTPException(400, "an invoice needs at least one line")
    case, created = store.ingest_invoice(body.entity, body.supplier, body.invoice_id, body.po_id,
                                         [l.model_dump() for l in body.lines], remarks=body.remarks)
    return {"created": created, "case": case_detail(case.id)}


@app.get("/api/erp/{entity}")
def erp_records(entity: str):
    if entity not in store.OWNERS:
        raise HTTPException(404, "unknown entity")
    e = store.erp(entity)
    return {"po_lines": [v.__dict__ for v in e["po_lines"].values()], "grns": [g.__dict__ for g in e["grns"]],
            "amendments": [a.__dict__ for a in e["amendments"]]}


@app.get("/api/cases/{case_id}/packet")
def packet(case_id: str):
    """The resolution packet: what a controller (or auditor) receives. Every assertion points at a record + hash."""
    case = get_case(case_id)
    return {
        "case": case.id, "entity": case.entity, "entity_name": store.ENTITY_NAMES[case.entity], "supplier": case.supplier,
        "invoice": case.invoice_id, "po": case.po_id, "status": case.status, "rules_version": store.RULES_VERSION,
        "totals": case.totals,
        "checks": [{"blocker": b.id, "type": b.type, "status": b.status, "cleared_by": b.cleared_by, "owner": b.owner_role,
                    "amount_at_risk": b.amount_at_risk, "evidence": b.evidence_ids} for b in case.blockers],
        "evidence": [{"id": e.id, "kind": e.kind, "trust": e.trust, "source": e.source, "version": e.version,
                      "hash": e.content_hash, "summary": e.summary} for e in case.evidence],
        "requests": [{"id": d.id, "to": d.recipient, "status": d.status, "cites": d.cited_evidence, "author": d.author} for d in case.drafts],
        "planner_runs": [t for t in case.agent_trace if t.get("meta")],
        "statement": "Evidence complete is not payment authorised. The ERP approval flow decides what is paid.",
        "audit_events": len(case.audit),
    }


@app.post("/api/cases/{case_id}/close")
def close_case(case_id: str):
    """Reviewer sends the resolution packet into the existing approval flow. Evidence complete != payment authorised."""
    case = get_case(case_id)
    if any(b.status == "open" for b in case.blockers):
        raise HTTPException(409, "open blockers remain; packet cannot be sent")
    case.packet = packet(case_id)
    case.status = "closed"
    store.audit(case, "reviewer", "packet.sent", "resolution packet handed to ERP approval workflow (no payment initiated)")
    return case_detail(case_id)


@app.get("/api/eval")
def run_eval(planners: str = "scripted", refresh: bool = False):
    modes = tuple(p for p in planners.split(",") if p in ("scripted", "llm", "redteam"))
    key = ",".join(modes)
    if refresh or key not in _EVAL_CACHE:
        _EVAL_CACHE[key] = evaluation.evaluate(modes)
    return _EVAL_CACHE[key]


@app.post("/api/reset")
def reset():
    store.seed()
    return {"ok": True}
