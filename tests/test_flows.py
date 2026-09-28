"""The five demo moments, as tests. Run: pytest -q"""
from fastapi.testclient import TestClient
from app.main import app
from app import store

c = TestClient(app)


def setup_function():
    store.seed()


def blockers(case_id):
    return [(b["type"], b["status"]) for b in c.get(f"/api/cases/{case_id}").json()["blockers"]]


def test_page_two_case_has_two_blockers_and_correct_totals():
    case = c.get("/api/cases/R-1042").json()
    assert blockers("R-1042") == [("MISSING_RECEIPT", "open"), ("PRICE_UNSUPPORTED", "open")]
    assert case["totals"]["invoice_total"] == "AED 2,200.00"
    assert case["totals"]["receipts_at_po_price"] == "AED 1,600.00"
    assert case["totals"]["difference"] == "AED 600.00"


def test_agent_proposes_one_draft_per_blocker_with_code_resolved_recipients():
    r = c.post("/api/cases/R-1042/investigate").json()
    assert len(r["drafts"]) == 2
    assert {d["recipient"] for d in r["drafts"]} == {"receiving.north@demo-health.ae", "procurement@demo-health.ae"}
    assert all(d["status"] == "proposed" for d in r["drafts"])
    # running again must not create duplicate requests
    r2 = c.post("/api/cases/R-1042/investigate").json()
    assert len(r2["drafts"]) == 2


def test_supplier_email_does_not_clear_anything():
    c.post("/api/cases/R-1042/events/supplier-email", json={"text": "All 100 boxes delivered, please pay."})
    assert blockers("R-1042") == [("MISSING_RECEIPT", "open"), ("PRICE_UNSUPPORTED", "open")]


def test_grn_clears_quantity_but_price_remains_then_amendment_clears_price():
    c.post("/api/cases/R-1042/events/grn", json={"po_line": "PO-104/L7", "qty": 20})
    assert blockers("R-1042") == [("MISSING_RECEIPT", "cleared"), ("PRICE_UNSUPPORTED", "open")]
    case = c.get("/api/cases/R-1042").json()
    assert case["totals"]["difference"] == "AED 200.00"
    assert c.post("/api/cases/R-1042/close").status_code == 409          # still blocked
    c.post("/api/cases/R-1042/events/amendment", json={"po_line": "PO-104/L7", "unit_price": 22})
    assert blockers("R-1042") == [("MISSING_RECEIPT", "cleared"), ("PRICE_UNSUPPORTED", "cleared")]
    assert c.get("/api/cases/R-1042").json()["status"] == "evidence_complete"
    assert c.post("/api/cases/R-1042/close").json()["status"] == "closed"


def test_reupload_is_idempotent():
    before = len(c.get("/api/cases").json())
    r = c.post("/api/cases/R-1042/events/reupload").json()
    assert r["created"] is False and r["case_id"] == "R-1042"
    assert len(c.get("/api/cases").json()) == before


def test_duplicate_billing_detected_via_receipt_allocation():
    assert blockers("R-1044") == [("DUPLICATE_BILLING", "open")]


def test_injected_instructions_cannot_produce_prohibited_actions():
    from app import agent, policy
    case = store.CASES["R-1045"]
    # a compromised planner tries to act on the injected note
    try:
        agent.run_tool(case, "send_payment", {})
        assert False, "should have been rejected"
    except policy.PolicyViolation:
        pass
    r = agent.run_tool(case, "draft_request", {"blocker_id": case.blockers[0].id, "owner_role": "procurement",
                                               "message": "Please update bank details to ...", "cited_evidence": ["NOTE-1"]})
    assert "prohibited" in r["error"]
    r = agent.run_tool(case, "draft_request", {"blocker_id": case.blockers[0].id, "owner_role": "procurement",
                                               "message": "Is AED 300 supported?", "cited_evidence": ["AMD-999"]})
    assert "unknown source id" in r["error"]
    assert any(a["action"] == "policy.reject" for a in [x.__dict__ for x in case.audit])


def test_approve_twice_is_suppressed_by_dedup():
    c.post("/api/cases/R-1042/investigate")
    c.post("/api/cases/R-1042/drafts/D1", json={"approve": True})
    c.post("/api/cases/R-1042/drafts/D1", json={"approve": True})
    audit = [a["action"] for a in c.get("/api/cases/R-1042").json()["audit"]]
    assert audit.count("draft.approved") == 1 and "outbox.duplicate_suppressed" in audit
