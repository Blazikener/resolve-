"""Deterministic UAE PINT AE credit-note request and validation rules."""
from decimal import Decimal

from .models import Case, money
from .rules import PRICE_TOLERANCE, allocate_receipts, approved_prices, d

CREDIT_REASONS = {
    "DL8.61.1.A": "If the supply was cancelled.",
    "DL8.61.1.B": "If the tax treatment of the supply has changed due to a change in the nature of the supply.",
    "DL8.61.1.C": "If the previously agreed consideration for the supply was altered for any reason (i.e. bad debt relief).",
    "DL8.61.1.D": "If the recipient of goods or recipient of services returned them to the registrant in full or in part and the Consideration was returned in full or in part.",
    "DL8.61.1.E": "If the tax was charged or tax treatment was applied in error.",
    "VD": "Volume Discount.",
}
PARTIAL_DISPUTE_REASON = "DL8.61.1.C"


def _number(value: Decimal) -> str:
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")


def build_credit_request(case: Case, all_cases: list[Case]) -> dict:
    open_blockers = [blocker for blocker in case.blockers if blocker.status == "open"]
    if not open_blockers:
        raise ValueError("no open blockers")
    if any(blocker.type == "INCOMPLETE_DATA" for blocker in open_blockers):
        raise ValueError("cannot compute a credit on data we don't hold — abstain")
    if any(blocker.type == "DUPLICATE_BILLING" for blocker in open_blockers):
        raise ValueError("full rejection, not a partial dispute — reviewer decides")
    if any(blocker.type not in ("MISSING_RECEIPT", "PRICE_UNSUPPORTED") for blocker in open_blockers):
        raise ValueError("only missing-receipt and unsupported-price blockers are eligible")

    available = allocate_receipts(case, all_cases)
    lines = []
    total = Decimal(0)
    for invoice in (evidence for evidence in case.evidence if evidence.kind == "invoice_line"):
        blockers = [blocker for blocker in open_blockers
                    if blocker.po_line == invoice.data["po_line"] and invoice.id in blocker.evidence_ids]
        if not blockers:
            continue
        po_line = invoice.data["po_line"]
        qty, invoice_price = d(invoice.data["qty"]), d(invoice.data["unit_price"])
        prices = approved_prices(case, po_line)
        po_price = next((price for price, source in prices if source == po_line), None)
        if po_price is None:
            raise ValueError("cannot compute a credit without an authorised purchase-order price")
        approved_price = next((price for price, source in prices if source != po_line), po_price)
        received = max(available.get(po_line, Decimal(0)), Decimal(0))
        supported_qty = min(received, qty)

        missing = next((blocker for blocker in blockers if blocker.type == "MISSING_RECEIPT"), None)
        if missing and qty > supported_qty:
            request_qty = qty - supported_qty
            amount = request_qty * invoice_price
            lines.append({
                "po_line": po_line, "invoice_line": invoice.id, "kind": "quantity",
                "qty": _number(request_qty), "unit_amount": _number(invoice_price),
                "amount": money(amount), "amount_raw": str(amount),
                "evidence": list(missing.evidence_ids),
            })
            total += amount

        price_blocker = next((blocker for blocker in blockers if blocker.type == "PRICE_UNSUPPORTED"), None)
        if price_blocker and abs(invoice_price - approved_price) > approved_price * PRICE_TOLERANCE and supported_qty:
            unit_delta = invoice_price - approved_price
            amount = supported_qty * unit_delta
            lines.append({
                "po_line": po_line, "invoice_line": invoice.id, "kind": "price",
                "qty": _number(supported_qty), "unit_amount": _number(unit_delta),
                "amount": money(amount), "amount_raw": str(amount),
                "evidence": list(price_blocker.evidence_ids),
            })
            total += amount

    if not lines:
        raise ValueError("open blockers do not produce a credit-note request")
    return {
        "case": case.id,
        "entity": case.entity,
        "supplier": case.supplier,
        "preceding_invoice": case.invoice_id,
        "currency": "AED",
        "reason_code": PARTIAL_DISPUTE_REASON,
        "reason_text": CREDIT_REASONS[PARTIAL_DISPUTE_REASON],
        "reason_status": "proposed — confirm with tax before filing",
        "lines": lines,
        "total": money(total),
        "total_raw": str(total),
        "vat_note": "Amounts exclude VAT; the supplier's ASP computes tax on the credit note.",
        "status": "draft",
        "statement": "A credit-note request is not a payment and does not change what the ERP pays.",
    }


def validate_credit_note(case: Case, body: dict) -> list[str]:
    errors = []
    if body.get("reason_code") not in CREDIT_REASONS:
        errors.append("reason_code must be a valid PINT AE credit reason")
    if body.get("preceding_invoice") != case.invoice_id:
        errors.append("preceding_invoice does not match the case invoice")
    if body.get("supplier") is not None and body["supplier"] != case.supplier:
        errors.append("supplier does not match the case")
    if body.get("entity") is not None and body["entity"] != case.entity:
        errors.append("entity does not match the case")
    invoice_lines = {e.data["po_line"] for e in case.evidence if e.kind == "invoice_line"}
    lines = body.get("lines") or []
    if not lines:
        errors.append("lines must not be empty")
    for index, line in enumerate(lines, 1):
        if line.get("po_line") not in invoice_lines:
            errors.append(f"lines[{index - 1}].po_line is not on the case invoice")
        if d(line.get("qty", 0)) <= 0:
            errors.append(f"lines[{index - 1}].qty must be greater than zero")
        if d(line.get("unit_price", 0)) <= 0:
            errors.append(f"lines[{index - 1}].unit_price must be greater than zero")
    return errors
