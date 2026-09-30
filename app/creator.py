"""Standalone creator revenue pilot: uvicorn app.creator:app."""

import csv
import io
import os
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import quote
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import creator_billing as billing
from . import creator_store as store
from .creator_models import (
    Acceptance,
    Activity,
    Credentials,
    License,
    LicenseEdit,
    LicenseInput,
    Payment,
    PaymentInput,
    Renewal,
    Signup,
    User,
    Workspace,
)

STATIC = Path(__file__).resolve().parent.parent / "static"
COOKIE = "resolve_session"


class BodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        chunks: list[bytes] = []
        length = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            length += len(chunk)
            if length > 131072:
                await JSONResponse(
                    {"detail": "Request is too large."}, status_code=413
                )(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def bounded_receive() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": b"".join(chunks),
                    "more_body": False,
                }
            return await receive()

        await self.app(scope, bounded_receive, send)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    store.initialize()
    yield


app = FastAPI(title="Resolve · Creator renewals", lifespan=lifespan)
app.add_middleware(BodyLimit)


@app.middleware("http")
async def security(request: Request, call_next: RequestResponseEndpoint) -> Response:
    origin = request.headers.get("origin")
    expected = os.environ.get("RESOLVE_PUBLIC_URL", str(request.base_url).rstrip("/"))
    if (
        request.method not in ("GET", "HEAD", "OPTIONS")
        and origin
        and origin != expected
    ):
        return JSONResponse(
            {"detail": "Cross-origin writes are not allowed."}, status_code=403
        )
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    if expected.startswith("https://"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


def current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE, "")
    user = store.session_user(token)
    if request.method not in ("GET", "HEAD"):
        expected = store.token_hash("csrf:" + token)
        if not secrets.compare_digest(
            request.headers.get("x-csrf-token", ""), expected
        ):
            raise HTTPException(403, "Refresh the page and try again.")
    return user


app.include_router(billing.router(current_user))


def begin_session(response: Response, user: User, request: Request) -> None:
    old = request.cookies.get(COOKIE, "")
    if old:
        with store.db() as c:
            c.execute("DELETE FROM sessions WHERE hash=?", (store.token_hash(old),))
    token = store.session(user)
    secure = (
        os.environ.get("RESOLVE_PUBLIC_URL", "").startswith("https://")
        or request.url.scheme == "https"
    )
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=secure,
        samesite="strict",
        max_age=86400 if user.demo else 604800,
    )


def auth_limit(request: Request, email: str = "") -> None:
    store.throttle(
        "auth-ip:" + (request.client.host if request.client else "unknown"), 40
    )
    if email:
        store.throttle("auth-email:" + email, 15)


@app.get("/")
@app.get("/app")
def index() -> FileResponse:
    return FileResponse(STATIC / "creator.html")


@app.get("/assets/creator.css")
def css() -> FileResponse:
    return FileResponse(STATIC / "creator.css")


@app.get("/assets/creator.js")
def javascript() -> FileResponse:
    return FileResponse(STATIC / "creator.js")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/signup", status_code=201)
def signup(body: Signup, request: Request, response: Response) -> dict[str, bool]:
    auth_limit(request, body.email)
    user = store.create_user(body.email, body.name, body.password)
    begin_session(response, user, request)
    return {"ok": True}


@app.post("/api/login")
def login(body: Credentials, request: Request, response: Response) -> dict[str, bool]:
    auth_limit(request, body.email)
    user = store.authenticate(body.email, body.password)
    begin_session(response, user, request)
    return {"ok": True}


@app.post("/api/demo")
def demo(request: Request, response: Response) -> dict[str, bool]:
    auth_limit(request)
    user = store.create_user(
        f"{uuid4().hex}@demo.invalid",
        "Alex Morgan",
        secrets.token_urlsafe(32),
        demo=True,
    )
    store.seed_demo(user)
    begin_session(response, user, request)
    return {"ok": True}


@app.post("/api/logout")
def logout(
    request: Request, response: Response, user: User = Depends(current_user)
) -> dict[str, bool]:
    with store.db() as c:
        c.execute(
            "DELETE FROM sessions WHERE hash=?",
            (store.token_hash(request.cookies.get(COOKIE, "")),),
        )
        if user.demo:
            c.execute("DELETE FROM users WHERE id=?", (user.id,))
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/api/workspace")
def workspace(request: Request, user: User = Depends(current_user)) -> Workspace:
    with store.db() as c:
        return Workspace(
            user=user,
            csrf=store.token_hash("csrf:" + request.cookies.get(COOKIE, "")),
            today=store.today(),
            licenses=[
                License.model_validate_json(r)
                for r in store.records(c, user.id, "license")
            ],
            renewals=[
                Renewal.model_validate_json(r)
                for r in store.records(c, user.id, "renewal")
            ],
            payments=[
                Payment.model_validate_json(r)
                for r in store.records(c, user.id, "payment")
            ],
            activity=[
                Activity.model_validate_json(r)
                for r in store.records(c, user.id, "activity")
            ][:100],
            billing_available=billing.available(),
        )


@app.post("/api/licenses", status_code=201)
def add_license(body: LicenseInput, user: User = Depends(current_user)) -> License:
    with store.db() as c:
        return store.add_license(c, store.user_by_id(c, user.id), body)


@app.put("/api/licenses/{license_id}")
def edit_license(
    license_id: str, body: LicenseEdit, user: User = Depends(current_user)
) -> License:
    with store.db() as c:
        old = License.model_validate_json(store.get(c, user.id, license_id, "license"))
        if old.revision != body.revision:
            raise HTTPException(409, "This license changed. Refresh before editing.")
        if old.archived and not body.archived:
            active = sum(
                not License.model_validate_json(raw).archived
                for raw in store.records(c, user.id, "license")
            )
            limit = (
                10
                if user.demo
                else (2000 if store.user_by_id(c, user.id).plan == "pro" else 3)
            )
            if active >= limit:
                raise HTTPException(
                    402, "Archive another license or upgrade before restoring this one."
                )
        item = License(
            id=old.id,
            **body.model_dump(exclude={"revision"}),
            revision=old.revision + 1,
        )
        store.save(c, user.id, item, "license")
        store.activity(
            c,
            user.id,
            item.id,
            f"Creator updated license: {item.starts_on} to {item.expires_on}. Scope: {item.scope}",
        )
        return item


@app.post("/api/licenses/{license_id}/propose", status_code=201)
def propose(license_id: str, user: User = Depends(current_user)) -> Renewal:
    with store.db() as c:
        item = License.model_validate_json(store.get(c, user.id, license_id, "license"))
        if item.archived:
            raise HTTPException(409, "Restore this license before proposing a renewal.")
        for raw in store.records(c, user.id, "renewal"):
            old = Renewal.model_validate_json(raw)
            if old.license_id == license_id and old.status == "draft":
                if old.license_revision == item.revision:
                    return old
                raise HTTPException(
                    409,
                    "Close the existing draft before creating an offer with updated terms.",
                )
        start = max(item.expires_on + timedelta(days=1), store.today())
        end = start + timedelta(days=item.renewal_days - 1)
        if end.year > 2100:
            raise HTTPException(422, "Renewal dates must be before 2101.")
        renewal = Renewal(
            id=uuid4().hex,
            license_id=item.id,
            license_revision=item.revision,
            brand=item.brand,
            title=item.title,
            contact_email=item.contact_email,
            scope=item.scope,
            starts_on=start,
            expires_on=end,
            fee_cents=item.renewal_fee_cents,
            contract_url=item.contract_url,
            content_url=item.content_url,
            created_at=store.now(),
        )
        store.save(c, user.id, renewal, "renewal")
        store.activity(
            c,
            user.id,
            item.id,
            "Renewal draft created. No message sent; no revenue booked.",
        )
        return renewal


@app.post("/api/renewals/{renewal_id}/accept")
def accept(
    renewal_id: str, body: Acceptance, user: User = Depends(current_user)
) -> Renewal:
    with store.db() as c:
        renewal = Renewal.model_validate_json(
            store.get(c, user.id, renewal_id, "renewal")
        )
        if renewal.status != "draft":
            raise HTTPException(409, "Only an open draft can be confirmed.")
        item = License.model_validate_json(
            store.get(c, user.id, renewal.license_id, "license")
        )
        if item.revision != renewal.license_revision or item.archived:
            raise HTTPException(
                409, "License terms changed. Close this draft and create a new offer."
            )
        if body.due_on < store.today() or body.due_on.year > 2100:
            raise HTTPException(
                422, "Payment due date must be today or later, before 2101."
            )
        renewal.status = "accepted"
        renewal.due_on = body.due_on
        renewal.approval_note = body.approval_note
        item.starts_on = renewal.starts_on
        item.expires_on = renewal.expires_on
        item.revision += 1
        store.save(c, user.id, renewal, "renewal")
        store.save(c, user.id, item, "license")
        store.activity(
            c,
            user.id,
            item.id,
            "Brand approval recorded by creator; license extended. Payment not yet received.",
        )
        return renewal


@app.post("/api/renewals/{renewal_id}/decline")
def decline(renewal_id: str, user: User = Depends(current_user)) -> Renewal:
    with store.db() as c:
        renewal = Renewal.model_validate_json(
            store.get(c, user.id, renewal_id, "renewal")
        )
        if renewal.status != "draft":
            raise HTTPException(409, "Only an open draft can be closed.")
        renewal.status = "declined"
        store.save(c, user.id, renewal, "renewal")
        store.activity(
            c, user.id, renewal.license_id, "Draft closed without a renewal."
        )
        return renewal


@app.post("/api/renewals/{renewal_id}/payments", status_code=201)
def record_payment(
    renewal_id: str, body: PaymentInput, user: User = Depends(current_user)
) -> Payment:
    with store.db() as c:
        renewal = Renewal.model_validate_json(
            store.get(c, user.id, renewal_id, "renewal")
        )
        if renewal.status != "accepted":
            raise HTTPException(
                409, "Confirm the brand's approval before recording a payment."
            )
        for raw in store.records(c, user.id, "payment"):
            existing = Payment.model_validate_json(raw)
            if existing.idempotency_key == body.idempotency_key:
                if (
                    existing.renewal_id != renewal_id
                    or existing.amount_cents != body.amount_cents
                    or existing.reference != body.reference
                ):
                    raise HTTPException(
                        409,
                        "This payment reference was already used for a different request.",
                    )
                return existing
        if body.amount_cents > renewal.fee_cents - store.paid(c, user.id, renewal_id):
            raise HTTPException(422, "Payment exceeds the outstanding balance.")
        payment = Payment(
            id=uuid4().hex,
            renewal_id=renewal_id,
            **body.model_dump(),
            created_at=store.now(),
        )
        store.save(c, user.id, payment, "payment")
        store.activity(
            c,
            user.id,
            renewal.license_id,
            f"Creator recorded USD {body.amount_cents / 100:.2f} received. Not bank verified.",
        )
        return payment


@app.post("/api/payments/{payment_id}/reverse")
def reverse_payment(payment_id: str, user: User = Depends(current_user)) -> Payment:
    with store.db() as c:
        payment = Payment.model_validate_json(
            store.get(c, user.id, payment_id, "payment")
        )
        renewal = Renewal.model_validate_json(
            store.get(c, user.id, payment.renewal_id, "renewal")
        )
        if not payment.reversed:
            payment.reversed = True
            store.save(c, user.id, payment, "payment")
            store.activity(
                c,
                user.id,
                renewal.license_id,
                "Payment entry reversed by creator. No funds moved.",
            )
        return payment


@app.get("/api/renewals/{renewal_id}/draft")
def draft(renewal_id: str, user: User = Depends(current_user)) -> dict[str, str]:
    with store.db() as c:
        renewal = Renewal.model_validate_json(
            store.get(c, user.id, renewal_id, "renewal")
        )
        balance = renewal.fee_cents - store.paid(c, user.id, renewal_id)
    if renewal.status == "declined" or (renewal.status == "accepted" and balance == 0):
        raise HTTPException(409, "There is no open follow-up for this renewal.")
    if renewal.status == "draft":
        subject = f"Usage renewal proposal · {renewal.title}"
        body = (
            f"Hi {renewal.brand} team,\n\nWould you like to renew usage of {renewal.title}?\n\n"
            f"Proposed scope: {renewal.scope}\nProposed dates: {renewal.starts_on} through {renewal.expires_on} (inclusive)\n"
            f"Proposed fee: USD {renewal.fee_cents / 100:.2f}\n\nPlease confirm these terms in writing before any extension. "
        )
    else:
        subject = f"Payment follow-up · {renewal.title}"
        body = (
            f"Hi {renewal.brand} team,\n\nI'm following up on the renewal for {renewal.title}. "
            f"My records show USD {balance / 100:.2f} outstanding, due {renewal.due_on}.\n\n"
            "Could you confirm the expected payment date? If payment is already on its way, please send the reference so I can update my records. "
        )
    if renewal.content_url:
        body += f"\n\nContent reference: {renewal.content_url}"
    body += f"\n\nThank you,\n{user.name}"
    return {
        "to": renewal.contact_email,
        "subject": subject,
        "body": body,
        "mailto": f"mailto:{quote(renewal.contact_email)}?subject={quote(subject)}&body={quote(body)}",
    }


@app.get("/api/licenses/{license_id}/packet")
def packet(license_id: str, user: User = Depends(current_user)) -> Response:
    with store.db() as c:
        item = License.model_validate_json(store.get(c, user.id, license_id, "license"))
        renewals = [
            Renewal.model_validate_json(r) for r in store.records(c, user.id, "renewal")
        ]
        payments = [
            Payment.model_validate_json(r) for r in store.records(c, user.id, "payment")
        ]
        lines = [
            "RESOLVE — CREATOR RECORD",
            f"Exported {store.now()}",
            "",
            f"Brand: {item.brand}",
            f"Content: {item.title}",
            f"Scope: {item.scope}",
            f"Current term: {item.starts_on} to {item.expires_on}",
            f"Contract reference: {item.contract_url or 'Not supplied'}",
            f"Content reference: {item.content_url or 'Not supplied'}",
            f"Creator notes: {item.notes}",
            "",
            "RENEWAL HISTORY",
        ]
        for renewal in renewals:
            if renewal.license_id == item.id:
                lines += [
                    f"{renewal.id} | {renewal.status} | {renewal.starts_on} to {renewal.expires_on}",
                    f"{renewal.brand} | {renewal.title} | {renewal.scope}",
                    f"Agreement: {renewal.contract_url or 'Not supplied'}; content: {renewal.content_url or 'Not supplied'}",
                    f"Fee USD {renewal.fee_cents / 100:.2f}; recorded received USD {store.paid(c, user.id, renewal.id) / 100:.2f}",
                    f"Due: {renewal.due_on}; creator-recorded approval: {renewal.approval_note or 'None'}",
                ]
                for payment in payments:
                    if payment.renewal_id == renewal.id:
                        lines.append(
                            f"Payment {payment.id} | {payment.created_at} | USD {payment.amount_cents / 100:.2f} | {payment.reference} | {'reversed' if payment.reversed else 'creator-reported received'}"
                        )
        lines += ["", "ACTIVITY"]
        for raw in store.records(c, user.id, "activity"):
            event = Activity.model_validate_json(raw)
            if event.license_id == item.id:
                lines.append(f"{event.created_at} | {event.text}")
        lines += [
            "",
            "All terms, evidence links, approvals and payments are creator-provided, not independently verified.",
            "An expired date does not establish ongoing ad use or infringement. Draft offers are not receivables.",
        ]
    return Response(
        "\n".join(lines),
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="resolve-{item.id[:8]}.txt"'
        },
    )


def csv_cell(value: str) -> str:
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n"))
        or value.startswith(("\t", "\r", "\n"))
        else value
    )


@app.get("/api/export")
def export(user: User = Depends(current_user)) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "brand",
            "content",
            "status",
            "start",
            "end",
            "fee_usd",
            "received_usd_creator_reported",
            "due",
            "approval_note",
        ]
    )
    with store.db() as c:
        for raw in store.records(c, user.id, "renewal"):
            r = Renewal.model_validate_json(raw)
            writer.writerow(
                [
                    csv_cell(r.brand),
                    csv_cell(r.title),
                    r.status,
                    r.starts_on,
                    r.expires_on,
                    f"{r.fee_cents / 100:.2f}",
                    f"{store.paid(c, user.id, r.id) / 100:.2f}",
                    r.due_on,
                    csv_cell(r.approval_note),
                ]
            )
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="resolve-renewals.csv"'},
    )
