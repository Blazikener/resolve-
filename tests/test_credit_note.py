"""UAE PINT AE partial-dispute credit-note request and ASP evidence flows."""
import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app

c = TestClient(app)


def setup_function():
    store.seed()


def test_r1042_preview_builds_quantity_and_price_request_without_sensitive_keys():
    response = c.get("/api/cases/R-1042/credit-note-request")
    assert response.status_code == 200
    request = response.json()
    assert [(line["kind"], line["amount"]) for line in request["lines"]] == [
        ("quantity", "AED 440.00"), ("price", "AED 160.00")
    ]
    assert request["total"] == "AED 600.00"
    assert request["reason_code"] == "DL8.61.1.C"

    def assert_safe_keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                assert not any(term in key.lower() for term in ("pay", "iban", "bank"))
                assert_safe_keys(child)
        elif isinstance(value, list):
            for child in value:
                assert_safe_keys(child)

    assert_safe_keys(request)


def test_r1054_preview_matches_seeded_credit_split():
    request = c.get("/api/cases/R-1054/credit-note-request").json()
    assert [(line["qty"], line["unit_amount"], line["amount"]) for line in request["lines"]] == [
        ("10", "48", "AED 480.00"), ("50", "3", "AED 150.00")
    ]
    assert request["total"] == "AED 630.00"


@pytest.mark.parametrize("case_id", ["R-1043", "R-1044", "R-1049"])
def test_ineligible_cases_return_conflict(case_id):
    response = c.get(f"/api/cases/{case_id}/credit-note-request")
    assert response.status_code == 409
    assert response.json()["detail"]


def test_credit_request_approval_is_audited_and_idempotent():
    first = c.post("/api/cases/R-1042/credit-note-request", json={"approved_by": "reviewer.one"})
    assert first.status_code == 200
    assert first.json()["approved_by"] == "reviewer.one"
    case = c.get("/api/cases/R-1042").json()
    assert case["status"] == "open"
    assert [a["action"] for a in case["audit"]].count("credit_note.request.approved") == 1

    second = c.post("/api/cases/R-1042/credit-note-request").json()
    case = c.get("/api/cases/R-1042").json()
    assert second["total_raw"] == first.json()["total_raw"]
    assert [a["action"] for a in case["audit"]].count("credit_note.request.approved") == 1
    assert [a["action"] for a in case["audit"]].count("credit_note.request.duplicate") == 1


def test_exact_credit_note_clears_blockers_and_packet_keeps_request():
    c.post("/api/cases/R-1054/credit-note-request")
    response = c.post("/api/cases/R-1054/events/credit-note", json={
        "credit_note_id": "CN-501",
        "reason_code": "DL8.61.1.C",
        "preceding_invoice": "INV-227",
        "lines": [
            {"po_line": "PO-162/L1", "qty": 10, "unit_price": 48},
            {"po_line": "PO-162/L1", "qty": 50, "unit_price": 3},
        ],
    })
    assert response.status_code == 200
    case = response.json()
    assert case["status"] == "evidence_complete"
    assert len(case["blockers"]) == 2
    assert all(blocker["status"] == "cleared" for blocker in case["blockers"])
    assert all(blocker["cleared_by"].startswith("CN-501") for blocker in case["blockers"])
    assert case["totals"]["credited"] == "AED 630.00"
    assert case["totals"]["difference"] == "AED 0.00"

    assert c.post("/api/cases/R-1054/close").status_code == 200
    packet = c.get("/api/cases/R-1054/packet").json()
    assert packet["credit_request"]["status"] == "approved_for_supplier"


def test_partial_credit_does_not_clear_blockers():
    response = c.post("/api/cases/R-1054/events/credit-note", json={
        "reason_code": "DL8.61.1.C",
        "preceding_invoice": "INV-227",
        "lines": [{"po_line": "PO-162/L1", "qty": 10, "unit_price": 48}],
    })
    assert response.status_code == 200
    case = response.json()
    assert case["status"] == "open"
    assert [blocker["status"] for blocker in case["blockers"]] == ["open", "open"]
    assert case["totals"]["credited"] == "AED 480.00"
    assert case["totals"]["difference"] == "AED 150.00"


@pytest.mark.parametrize("changes", [
    {"preceding_invoice": "INV-WRONG"},
    {"reason_code": "BAD"},
    {"entity": "clinic-west"},
])
def test_invalid_credit_note_is_rejected_and_does_not_change_blockers(changes):
    case_before = c.get("/api/cases/R-1054").json()
    body = {
        "reason_code": "DL8.61.1.C",
        "preceding_invoice": "INV-227",
        "lines": [{"po_line": "PO-162/L1", "qty": 10, "unit_price": 48}],
    } | changes
    response = c.post("/api/cases/R-1054/events/credit-note", json=body)
    assert response.status_code == 422
    assert response.json()["errors"]
    case_after = c.get("/api/cases/R-1054").json()
    assert [(b["type"], b["status"]) for b in case_after["blockers"]] == [
        (b["type"], b["status"]) for b in case_before["blockers"]
    ]
    assert any(a["action"] == "credit_note.rejected" for a in case_after["audit"])


def test_same_credit_note_twice_is_recorded_once():
    body = {"credit_note_id": "CN-501", "reason_code": "DL8.61.1.C", "preceding_invoice": "INV-227",
            "lines": [{"po_line": "PO-162/L1", "qty": 10, "unit_price": 48}]}
    c.post("/api/cases/R-1054/events/credit-note", json=body)
    case = c.post("/api/cases/R-1054/events/credit-note", json=body).json()
    assert [e["id"] for e in case["evidence"] if e["kind"] == "credit_note_line"] == ["CN-501/L1"]
    assert case["totals"]["credited"] == "AED 480.00"
    assert any(a["action"] == "credit_note.duplicate" for a in case["audit"])
