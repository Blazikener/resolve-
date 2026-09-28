"""Policy gateway. Everything the agent proposes passes through here before it becomes real.

The model can *suggest* a link or a request. This code decides whether the suggestion is
allowed: does every cited record exist on this case, in this entity? Is the action permitted at
all? Who is the recipient (resolved from the ownership mapping, never from model text)?
"""
import re
from .models import Case, Draft
from .store import OWNERS, audit

ALLOWED_ACTIONS = {"read_case", "list_evidence", "find_amendments", "receipt_history", "draft_request", "finish"}
# Named so the audit trail can say *what* was attempted. None of these exist as tools; this is belt and braces.
KNOWN_PROHIBITED = {"send_email", "approve_payment", "release_payment", "update_bank_details", "update_supplier_master",
                    "open_case", "clear_blocker", "fetch_url", "run_sql"}
PROHIBITED_PATTERNS = (r"\bbank\b", r"\biban\b", r"\bpay now\b", r"\brelease (the )?payment\b", r"\bapprove (the )?payment\b",
                       r"\bswift\b", r"\baccount number\b", r"\bwire\b")


class PolicyViolation(Exception):
    pass


def verify_evidence_ids(case: Case, ids: list[str]) -> None:
    known = {e.id for e in case.evidence if e.entity == case.entity}
    unknown = [i for i in ids if i not in known]
    if unknown:
        audit(case, "policy", "policy.reject", f"draft cited unknown/cross-entity source id(s) {unknown}")
        raise PolicyViolation(f"unknown source id(s) {unknown} - the model cited evidence this case does not hold")


def check_action(case: Case, name: str) -> None:
    if name not in ALLOWED_ACTIONS:
        what = "known-prohibited" if name in KNOWN_PROHIBITED else "unknown"
        audit(case, "policy", "policy.reject", f"agent attempted {what} action '{name}' - no such tool is exposed")
        raise PolicyViolation(f"action '{name}' is not permitted; the agent has no such tool")


def make_draft(case: Case, blocker_id: str, owner_role: str, message: str, cited: list[str], author: str = "agent") -> Draft:
    blocker = next((b for b in case.blockers if b.id == blocker_id and b.status == "open"), None)
    if blocker is None:
        audit(case, "policy", "policy.reject", f"draft for '{blocker_id}': no such open blocker")
        raise PolicyViolation(f"no open blocker {blocker_id}")
    if owner_role != blocker.owner_role:
        audit(case, "policy", "policy.reject", f"draft for {blocker_id} addressed to '{owner_role}', owner is '{blocker.owner_role}'")
        raise PolicyViolation(f"blocker {blocker_id} is owned by '{blocker.owner_role}', not '{owner_role}'")
    if owner_role not in OWNERS[case.entity]:
        raise PolicyViolation(f"no owner mapping for role '{owner_role}' in {case.entity}")
    low = message.lower()
    hit = next((p for p in PROHIBITED_PATTERNS if re.search(p, low)), None)
    if hit:
        audit(case, "policy", "policy.reject", f"draft for {blocker_id} contained payment/bank language ({hit})")
        raise PolicyViolation("drafts may request evidence only; payment or bank-detail language is prohibited")
    verify_evidence_ids(case, cited)
    if not cited:
        raise PolicyViolation("a request must cite at least one evidence record")
    recipient = OWNERS[case.entity][owner_role]          # code decides who is asked
    dedup = f"{case.id}:{blocker_id}:{owner_role}"
    existing = next((d for d in case.drafts if d.dedup_key == dedup and d.status != "rejected"), None)
    if existing:
        audit(case, "policy", "policy.dedup", f"request for {blocker_id} already exists as {existing.id}; not duplicated")
        return existing                                    # same question, same owner -> never a second request
    draft = Draft(id=f"D{len(case.drafts)+1}", blocker_id=blocker_id, owner_role=owner_role, recipient=recipient,
                  message=message, cited_evidence=cited, dedup_key=dedup, author=author)
    case.drafts.append(draft)
    return draft
