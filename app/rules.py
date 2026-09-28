"""Deterministic checks. This is the 'money logic in code' half of the design.

Nothing in this file calls a model. Given the evidence on a case, it returns the same
blockers every time. The agent may *investigate*; only these rules decide what is proven.
"""
from decimal import Decimal
from .models import Case, Blocker, money

RULES_VERSION = "rules-2026.09.2"
PRICE_TOLERANCE = Decimal("0.005")     # 0.5 % - an agreed commercial tolerance, not a model guess


def d(x) -> Decimal:
    return Decimal(str(x))


def allocate_receipts(case: Case, all_cases: list[Case]) -> dict[str, Decimal]:
    """How much *authoritative* received quantity is available to this case, per PO line.

    Receipts already consumed by other invoices on the same PO line are subtracted, so the
    same delivery can never clear two invoices. Emails and notes contribute nothing here.
    """
    available: dict[str, Decimal] = {}
    for ev in case.evidence:
        if ev.kind == "grn_line" and ev.trust == "authoritative" and ev.entity == case.entity:
            available[ev.data["po_line"]] = available.get(ev.data["po_line"], Decimal(0)) + d(ev.data["qty"])
    for other in all_cases:
        if other.id == case.id or other.po_id != case.po_id or other.entity != case.entity:
            continue
        for ev in other.evidence:
            if ev.kind == "invoice_line" and other.status in ("evidence_complete", "closed"):
                pl = ev.data["po_line"]
                available[pl] = available.get(pl, Decimal(0)) - d(ev.data["qty"])
    # prior (already paid) invoices recorded on this case count as consumed too
    for ev in case.evidence:
        if ev.kind == "prior_invoice_line":
            pl = ev.data["po_line"]
            available[pl] = available.get(pl, Decimal(0)) - d(ev.data["qty"])
    return available


def approved_prices(case: Case, po_line: str) -> list[tuple[Decimal, str]]:
    """Unit prices we may accept for a PO line: the PO price plus any approved amendment."""
    prices = []
    for ev in case.evidence:
        if ev.entity != case.entity or ev.trust != "authoritative":
            continue
        if ev.kind == "po_line" and ev.id == po_line:
            prices.append((d(ev.data["unit_price"]), ev.id))
        if ev.kind == "amendment" and ev.data.get("po_line") == po_line and ev.data.get("approved") is True:
            prices.append((d(ev.data["unit_price"]), ev.id))
    return prices


def run_checks(case: Case, all_cases: list[Case]) -> list[Blocker]:
    """Recompute every blocker from scratch. Called on ingest and after every evidence change."""
    blockers: list[Blocker] = []
    available = allocate_receipts(case, all_cases)
    invoice_total = Decimal(0)
    receipts_at_po_price = Decimal(0)

    def new(type_, owner, question, amount, ids, pl):
        blockers.append(Blocker(id=f"{case.id}-B{len(blockers)+1}", type=type_, owner_role=owner, question=question,
                                amount_at_risk=money(amount), evidence_ids=ids, po_line=pl))

    for inv in [e for e in case.evidence if e.kind == "invoice_line"]:
        pl = inv.data["po_line"]
        qty, price = d(inv.data["qty"]), d(inv.data["unit_price"])
        invoice_total += qty * price
        prices = approved_prices(case, pl)
        po_price = next((p for p, src in prices if src == pl), None)

        # 0. Completeness: we cannot check what we do not hold. Abstain, do not guess.
        if po_price is None:
            new("INCOMPLETE_DATA", "ap_reviewer",
                f"{inv.id} references {pl}, but no purchase-order line for it is in the authorised feed. "
                f"Confirm the order reference or request the PO export; no commercial check can run until then.",
                qty * price, [inv.id], pl)
            continue

        received = max(available.get(pl, Decimal(0)), Decimal(0))
        # value the receipts at the price finance has approved: the PO price, or an approved amendment if one exists
        approved_price = next((p for p, src in prices if src != pl), po_price)
        receipts_at_po_price += min(received, qty) * approved_price
        grns = [e.id for e in case.evidence if e.kind == "grn_line" and e.data["po_line"] == pl and e.entity == case.entity]
        consumed = [e.id for e in case.evidence if e.kind == "prior_invoice_line" and e.data["po_line"] == pl]

        # 1. Quantity: invoiced more than we can prove was received?
        if qty > received:
            shortfall = qty - received
            if consumed and received <= 0:
                new("DUPLICATE_BILLING", "ap_reviewer",
                    f"The receipts on {pl} are already allocated to {', '.join(consumed)}. "
                    f"Is {inv.id} billing the same delivery again?",
                    shortfall * po_price, [inv.id, pl] + grns + consumed, pl)
            else:
                new("MISSING_RECEIPT", "receiving",
                    f"Were the remaining {shortfall:g} units on {pl} delivered? Record the receipt in the ERP, "
                    f"or confirm they are still outstanding.",
                    shortfall * po_price, [inv.id, pl] + grns, pl)

        # 2. Price: is the invoiced unit price supported by the PO or an approved amendment?
        supported = any(abs(price - p) <= p * PRICE_TOLERANCE for p, _ in prices)
        if not supported:
            new("PRICE_UNSUPPORTED", "procurement",
                f"Is {money(price)} per unit on {pl} supported by an approved order amendment? "
                f"Link the amendment, or request a corrected invoice from the supplier.",
                abs(price - po_price) * qty, [inv.id, pl] + [e.id for e in case.evidence if e.kind == "amendment"], pl)

    case.totals = {
        "invoice_total": money(invoice_total),
        "receipts_at_po_price": money(receipts_at_po_price),
        "difference": money(invoice_total - receipts_at_po_price),
        "invoice_total_raw": str(invoice_total),
        "note": "Difference is not proven loss, and not an instruction to pay the lower amount.",
    }
    return blockers


def merge_blockers(old: list[Blocker], new: list[Blocker], cleared_by: str | None) -> list[Blocker]:
    """Keep history: blockers that disappeared are marked cleared (by which evidence), not deleted."""
    key = lambda b: (b.type, b.owner_role, b.po_line)  # noqa: E731
    new_keys = {key(b) for b in new}
    merged = []
    for b in old:
        if b.status == "open" and key(b) not in new_keys:
            b.status, b.cleared_by = "cleared", cleared_by
        merged.append(b)
    existing = {key(b) for b in merged if b.status == "open"}
    for b in new:
        if key(b) not in existing:
            b.id = f"{new[0].id.rsplit('-B', 1)[0]}-B{len(merged)+1}"
            merged.append(b)
    return merged
