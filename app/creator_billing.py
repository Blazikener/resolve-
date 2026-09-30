"""Optional Stripe-hosted subscriptions. Entitlements come from Stripe state."""

import hashlib
import hmac
import os
import re
import time
from collections.abc import Callable
from typing import TypeVar
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from . import creator_store as store
from .creator_models import User

T = TypeVar("T", bound=BaseModel)


class Recurring(BaseModel):
    interval: str
    interval_count: int


class Price(BaseModel):
    id: str
    active: bool
    currency: str
    unit_amount: int | None
    recurring: Recurring | None


class Customer(BaseModel):
    id: str = Field(pattern=r"^cus_[a-zA-Z0-9]+$")


class Checkout(BaseModel):
    id: str = Field(pattern=r"^cs_[a-zA-Z0-9_]+$")
    status: str
    url: str | None = None


class Portal(BaseModel):
    url: str


class SubscriptionItem(BaseModel):
    price: Price


class SubscriptionItems(BaseModel):
    data: list[SubscriptionItem]


class Subscription(BaseModel):
    id: str
    customer: str
    status: str
    metadata: dict[str, str]
    items: SubscriptionItems


class Subscriptions(BaseModel):
    data: list[Subscription]
    has_more: bool


class EventObject(BaseModel):
    customer: str | None = None


class EventData(BaseModel):
    object: EventObject


class Event(BaseModel):
    id: str = Field(min_length=1, max_length=255)
    type: str
    data: EventData


def available() -> bool:
    public = urlsplit(os.environ.get("RESOLVE_PUBLIC_URL", ""))
    return bool(
        public.scheme in ("http", "https")
        and public.netloc
        and not public.path.strip("/")
        and not public.query
        and not public.fragment
        and all(
            os.environ.get(key)
            for key in ("STRIPE_SECRET_KEY", "STRIPE_PRICE_ID", "STRIPE_WEBHOOK_SECRET")
        )
    )


def configured() -> None:
    if not available():
        raise HTTPException(
            503, "Billing is not connected. The free workspace remains available."
        )


def stripe_request(
    method: str,
    path: str,
    result: type[T],
    fields: dict[str, str] | None = None,
    key: str = "",
) -> T:
    headers = {
        "Authorization": "Bearer " + os.environ["STRIPE_SECRET_KEY"],
        "Stripe-Version": "2025-03-31.basil",
    }
    if key:
        headers["Idempotency-Key"] = key
    try:
        response = httpx.request(
            method,
            "https://api.stripe.com/v1" + path,
            headers=headers,
            params=fields if method == "GET" else None,
            data=fields if method == "POST" else None,
            timeout=15,
        )
        response.raise_for_status()
        return result.model_validate(response.json())
    except (httpx.HTTPError, ValidationError, ValueError):
        raise HTTPException(
            502,
            "Stripe could not complete this request. Please try again or contact support.",
        ) from None


def monthly_pilot_price(price: Price) -> bool:
    return bool(
        price.currency == "usd"
        and price.unit_amount == 1900
        and price.recurring
        and price.recurring.interval == "month"
        and price.recurring.interval_count == 1
    )


def subscriptions(user: User) -> list[Subscription]:
    result = stripe_request(
        "GET",
        "/subscriptions",
        Subscriptions,
        {"customer": user.customer_id, "status": "all", "limit": "100"},
    )
    if result.has_more:
        raise HTTPException(
            503, "This billing account needs manual reconciliation. Contact support."
        )
    return [
        s
        for s in result.data
        if s.customer == user.customer_id
        and s.metadata.get("resolve_user_id") == user.id
        and any(
            i.price.id == os.environ["STRIPE_PRICE_ID"] and monthly_pilot_price(i.price)
            for i in s.items.data
        )
    ]


def hosted_url(url: str | None, host: str) -> str:
    parsed = urlsplit(url or "")
    if not url or parsed.scheme != "https" or parsed.netloc != host:
        raise HTTPException(502, "Stripe did not return a valid hosted billing page.")
    return url


def verify_event(payload: bytes, signature: str) -> Event:
    parts = [part.split("=", 1) for part in signature.split(",")]
    timestamps = [
        value
        for pair in parts
        if len(pair) == 2
        for name, value in [pair]
        if name == "t"
    ]
    signatures = [
        value
        for pair in parts
        if len(pair) == 2
        for name, value in [pair]
        if name == "v1"
    ]
    try:
        if len(timestamps) != 1 or abs(time.time() - int(timestamps[0])) > 300:
            raise ValueError
        signed = timestamps[0].encode() + b"." + payload
        digest = hmac.new(
            os.environ["STRIPE_WEBHOOK_SECRET"].encode(), signed, hashlib.sha256
        ).hexdigest()
        if not any(
            re.fullmatch(r"[a-f0-9]{64}", candidate)
            and hmac.compare_digest(digest, candidate)
            for candidate in signatures
        ):
            raise ValueError
        return Event.model_validate_json(payload)
    except (ValueError, ValidationError):
        raise HTTPException(
            400, "Invalid Stripe webhook signature or payload."
        ) from None


def reconcile(event: Event) -> None:
    accepted = {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "invoice.payment_succeeded",
        "invoice.payment_failed",
    }
    if event.type not in accepted or not event.data.object.customer:
        return
    with store.db() as c:
        if c.execute("SELECT 1 FROM billing_events WHERE id=?", (event.id,)).fetchone():
            return
        row = c.execute(
            "SELECT data FROM users WHERE json_extract(data, '$.customer_id')=?",
            (event.data.object.customer,),
        ).fetchone()
        if not row:
            return
        user = User.model_validate_json(row["data"])
        current = subscriptions(user)
        active = next((s for s in current if s.status in ("active", "trialing")), None)
        user.plan = "pro" if active and not user.demo else "free"
        user.subscription_id = active.id if active else ""
        store.save_user(c, user)
        c.execute("INSERT INTO billing_events VALUES (?)", (event.id,))


def router(current_user: Callable[[Request], User]) -> APIRouter:
    routes = APIRouter(prefix="/api/billing")

    @routes.post("/checkout")
    def checkout(user: User = Depends(current_user)) -> dict[str, str]:
        configured()
        if user.demo:
            raise HTTPException(403, "Create a real account before subscribing.")
        store.throttle("billing:" + user.id, 20)
        price_id = os.environ["STRIPE_PRICE_ID"]
        if not re.fullmatch(r"price_[a-zA-Z0-9]+", price_id):
            raise HTTPException(503, "Billing price is not configured correctly.")
        price = stripe_request("GET", "/prices/" + price_id, Price)
        if not price.active or not monthly_pilot_price(price):
            raise HTTPException(
                503,
                "Billing must use the advertised USD 19 monthly price. Contact support.",
            )
        public = os.environ["RESOLVE_PUBLIC_URL"].rstrip("/")
        with store.db() as c:
            user = store.user_by_id(c, user.id)
            if not user.customer_id:
                customer = stripe_request(
                    "POST",
                    "/customers",
                    Customer,
                    {
                        "email": user.email,
                        "name": user.name,
                        "metadata[resolve_user_id]": user.id,
                    },
                    key="resolve-customer-" + user.id,
                )
                user.customer_id = customer.id
                store.save_user(c, user)
        with store.db() as c:
            current = subscriptions(user)
            if any(s.status not in ("canceled", "incomplete_expired") for s in current):
                raise HTTPException(
                    409, "A subscription already exists. Use Manage billing instead."
                )
            existing = c.execute(
                "SELECT session_id FROM checkout_sessions WHERE user_id=?", (user.id,)
            ).fetchone()
            last_id = existing["session_id"] if existing else "first"
            if existing:
                previous = stripe_request(
                    "GET", "/checkout/sessions/" + last_id, Checkout
                )
                if previous.status == "open":
                    return {"url": hosted_url(previous.url, "checkout.stripe.com")}
                if previous.status == "complete" and not current:
                    raise HTTPException(
                        409,
                        "Checkout completed; subscription confirmation is pending. Try again shortly.",
                    )
            session = stripe_request(
                "POST",
                "/checkout/sessions",
                Checkout,
                {
                    "mode": "subscription",
                    "customer": user.customer_id,
                    "client_reference_id": user.id,
                    "line_items[0][price]": price_id,
                    "line_items[0][quantity]": "1",
                    "subscription_data[metadata][resolve_user_id]": user.id,
                    "success_url": public + "/app?billing=return",
                    "cancel_url": public + "/app?billing=cancel",
                },
                key=f"resolve-checkout-{user.id}-{last_id}",
            )
            url = hosted_url(session.url, "checkout.stripe.com")
            c.execute(
                "INSERT INTO checkout_sessions VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET session_id=excluded.session_id",
                (user.id, session.id),
            )
            return {"url": url}

    @routes.post("/portal")
    def portal(user: User = Depends(current_user)) -> dict[str, str]:
        configured()
        if user.demo or not user.customer_id:
            raise HTTPException(409, "This workspace has no billing account yet.")
        store.throttle("billing:" + user.id, 20)
        page = stripe_request(
            "POST",
            "/billing_portal/sessions",
            Portal,
            {
                "customer": user.customer_id,
                "return_url": os.environ["RESOLVE_PUBLIC_URL"].rstrip("/") + "/app",
            },
        )
        return {"url": hosted_url(page.url, "billing.stripe.com")}

    @routes.post("/webhook")
    async def webhook(request: Request) -> dict[str, bool]:
        configured()
        event = verify_event(
            await request.body(), request.headers.get("stripe-signature", "")
        )
        await run_in_threadpool(reconcile, event)
        return {"received": True}

    return routes
