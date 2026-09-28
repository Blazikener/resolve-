"""Plain data records. No behaviour here - just the shapes everything else agrees on."""
from dataclasses import dataclass, field, asdict
from decimal import Decimal
from typing import Literal, Optional


Trust = Literal["authoritative", "untrusted"]
# authoritative = came from a system of record (ERP/ASP) via an authorised feed.
# untrusted     = free text a human or supplier sent us (email, note, invoice remarks). Can inform, never prove.

BlockerType = Literal["MISSING_RECEIPT", "PRICE_UNSUPPORTED", "DUPLICATE_BILLING", "INCOMPLETE_DATA"]
OwnerRole = Literal["receiving", "procurement", "ap_reviewer"]


@dataclass
class Evidence:
    """One immutable fact we hold about a case. Every claim the system makes must point at one of these."""
    id: str                 # e.g. "PO-104/L7", "GRN-88/L3", "INV-218/L1", "AMD-12", "EMAIL-1"
    kind: Literal["po_line", "grn_line", "invoice_line", "amendment", "email", "prior_invoice_line"]
    entity: str             # legal entity the record belongs to (tenant boundary)
    trust: Trust
    summary: str            # human-readable "what the record says"
    data: dict = field(default_factory=dict)   # structured fields used by rules (qty, unit_price, po_line, ...)
    version: int = 1
    content_hash: str = ""
    source: str = "ERP"     # ERP / ASP / mailbox / invoice-text


@dataclass
class Blocker:
    id: str
    type: BlockerType
    owner_role: OwnerRole
    question: str           # the one thing the owner must answer
    amount_at_risk: str     # Decimal as string, for display
    evidence_ids: list[str] = field(default_factory=list)
    status: Literal["open", "cleared"] = "open"
    cleared_by: Optional[str] = None   # evidence id that cleared it
    po_line: str = ""


@dataclass
class Draft:
    """A proposed outbound request. Created by the agent, approved by a human, never auto-sent."""
    id: str
    blocker_id: str
    owner_role: str
    recipient: str          # resolved by CODE from the ownership mapping, never by the model
    message: str
    cited_evidence: list[str]
    status: Literal["proposed", "approved", "rejected"] = "proposed"
    dedup_key: str = ""
    author: str = "agent"   # planner label that wrote it


@dataclass
class AuditEvent:
    seq: int
    actor: Literal["system", "agent", "reviewer", "feed", "policy"]
    action: str
    detail: str
    rules_version: str
    model: str = "-"


@dataclass
class Case:
    id: str
    entity: str
    supplier: str
    invoice_id: str
    po_id: str
    received_at: str = ""   # ISO date the invoice entered the queue
    status: Literal["open", "evidence_complete", "closed"] = "open"
    evidence: list[Evidence] = field(default_factory=list)
    blockers: list[Blocker] = field(default_factory=list)
    drafts: list[Draft] = field(default_factory=list)
    audit: list[AuditEvent] = field(default_factory=list)
    agent_trace: list[dict] = field(default_factory=list)
    totals: dict = field(default_factory=dict)
    packet: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)


def money(x: Decimal) -> str:
    return f"AED {x.quantize(Decimal('0.01')):,}"
