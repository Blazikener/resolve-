"""No network or live charges: Stripe transport and raw signed events are fixtures."""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from app import creator_billing as billing
from app import creator_store as store

SECRET = "whsec_local_fixture_not_a_credential"


def price() -> dict[str, object]:
    return {
        "id": "price_pilot",
        "active": True,
        "currency": "usd",
        "unit_amount": 1900,
        "recurring": {"interval": "month", "interval_count": 1},
    }


@dataclass
class StripeFixture:
    user_id: str
    subscriptions: list[dict[str, object]] = field(default_factory=list)
    calls: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)
    price: dict[str, object] = field(default_factory=price)
    status: str = "open"
    fail: bool = False
    paginated: bool = False

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None,
        data: dict[str, str] | None,
        timeout: int,
    ) -> httpx.Response:
        path = urlsplit(url).path
        self.calls.append((method, path, data or params or {}))
        request = httpx.Request(method, url)
        assert headers["Stripe-Version"] == "2025-03-31.basil"
        if self.fail:
            return httpx.Response(
                500, json={"error": "private provider error"}, request=request
            )
        payload: dict[str, object]
        if path == "/v1/prices/price_pilot":
            payload = self.price
        elif path == "/v1/customers":
            assert headers["Idempotency-Key"] == "resolve-customer-" + self.user_id
            payload = {"id": "cus_creator"}
        elif path == "/v1/subscriptions":
            assert params == {
                "customer": "cus_creator",
                "status": "all",
                "limit": "100",
            }
            payload = {"data": self.subscriptions, "has_more": self.paginated}
        elif path == "/v1/checkout/sessions":
            assert data is not None
            assert data["customer"] == "cus_creator"
            assert data["mode"] == "subscription"
            assert data["line_items[0][price]"] == "price_pilot"
            assert data["subscription_data[metadata][resolve_user_id]"] == self.user_id
            assert data["success_url"] == "http://testserver/app?billing=return"
            assert "Idempotency-Key" in headers
            payload = {
                "id": "cs_test_fixture",
                "url": "https://checkout.stripe.com/c/pay/fixture",
                "status": "open",
            }
        elif path == "/v1/checkout/sessions/cs_test_fixture":
            payload = {
                "id": "cs_test_fixture",
                "url": "https://checkout.stripe.com/c/pay/fixture",
                "status": self.status,
            }
        elif path == "/v1/billing_portal/sessions":
            assert data is not None and data["customer"] == "cus_creator"
            payload = {"url": "https://billing.stripe.com/p/session/fixture"}
        else:
            raise AssertionError(f"Unexpected Stripe request: {method} {path}")
        return httpx.Response(200, json=payload, request=request)

    def subscription(
        self, status: str = "active", user_id: str = ""
    ) -> dict[str, object]:
        return {
            "id": "sub_fixture",
            "customer": "cus_creator",
            "status": status,
            "metadata": {"resolve_user_id": user_id or self.user_id},
            "items": {"data": [{"price": price()}]},
        }


@pytest.fixture
def stripe(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> StripeFixture:
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fixture")
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_pilot")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("RESOLVE_PUBLIC_URL", "http://testserver")
    response = client.post(
        "/api/signup",
        json={
            "email": "creator@example.com",
            "name": "Creator",
            "password": "a strong password",
        },
    )
    assert response.status_code == 201
    workspace = client.get("/api/workspace").json()
    client.headers["X-CSRF-Token"] = workspace["csrf"]
    fixture = StripeFixture(workspace["user"]["id"])
    monkeypatch.setattr(billing.httpx, "request", fixture.request)
    return fixture


def signed_event(
    client: TestClient,
    event_id: str = "evt_fixture",
    event_type: str = "customer.subscription.updated",
    timestamp: int | None = None,
    customer: str = "cus_creator",
) -> httpx.Response:
    payload = json.dumps(
        {"id": event_id, "type": event_type, "data": {"object": {"customer": customer}}}
    ).encode()
    stamp = str(timestamp if timestamp is not None else int(time.time()))
    signature = hmac.new(
        SECRET.encode(), stamp.encode() + b"." + payload, hashlib.sha256
    ).hexdigest()
    return client.post(
        "/api/billing/webhook",
        content=payload,
        headers={
            "Stripe-Signature": f"t={stamp},v1={signature}",
            "Content-Type": "application/json",
            "X-CSRF-Token": "",
        },
    )


def test_checkout_reuse_webhook_confirmation_and_portal(
    client: TestClient, stripe: StripeFixture
) -> None:
    assert client.get("/api/workspace").json()["billing_available"] is True
    first = client.post("/api/billing/checkout")
    assert first.status_code == 200 and first.json()["url"].startswith(
        "https://checkout.stripe.com/"
    )
    assert client.post("/api/billing/checkout").json() == first.json()
    assert (
        sum(
            method == "POST" and path == "/v1/checkout/sessions"
            for method, path, _ in stripe.calls
        )
        == 1
    )
    assert client.get("/api/workspace").json()["user"]["plan"] == "free"
    assert client.get("/app?billing=return").status_code == 200
    assert client.get("/api/workspace").json()["user"]["plan"] == "free"
    stripe.subscriptions = [stripe.subscription()]
    assert signed_event(client).status_code == 200
    assert client.get("/api/workspace").json()["user"]["plan"] == "pro"
    calls = len(stripe.calls)
    assert signed_event(client).status_code == 200
    assert len(stripe.calls) == calls
    assert client.post("/api/billing/checkout").status_code == 409
    assert (
        client.post("/api/billing/portal")
        .json()["url"]
        .startswith("https://billing.stripe.com/")
    )


def test_out_of_order_events_use_current_subscription_state(
    client: TestClient, stripe: StripeFixture
) -> None:
    client.post("/api/billing/checkout")
    stripe.subscriptions = [stripe.subscription()]
    assert (
        signed_event(
            client, "evt_old_delete", "customer.subscription.deleted"
        ).status_code
        == 200
    )
    assert client.get("/api/workspace").json()["user"]["plan"] == "pro"
    stripe.subscriptions = [stripe.subscription("past_due")]
    assert (
        signed_event(
            client, "evt_old_active", "customer.subscription.created"
        ).status_code
        == 200
    )
    assert client.get("/api/workspace").json()["user"]["plan"] == "free"
    stripe.subscriptions = [stripe.subscription("canceled")]
    assert signed_event(client, "evt_canceled").status_code == 200
    assert client.get("/api/workspace").json()["user"]["subscription_id"] == ""


def test_wrong_owner_price_or_customer_never_grants_pro(
    client: TestClient, stripe: StripeFixture
) -> None:
    client.post("/api/billing/checkout")
    stripe.subscriptions = [stripe.subscription(user_id="another_user")]
    assert signed_event(client, "evt_other_owner").status_code == 200
    assert client.get("/api/workspace").json()["user"]["plan"] == "free"
    stripe.subscriptions = [
        {
            **stripe.subscription(),
            "items": {"data": [{"price": {**price(), "id": "price_other"}}]},
        }
    ]
    assert signed_event(client, "evt_other_price").status_code == 200
    assert client.get("/api/workspace").json()["user"]["plan"] == "free"
    stripe.subscriptions = [stripe.subscription()]
    assert (
        signed_event(client, "evt_other_customer", customer="cus_other").status_code
        == 200
    )
    assert client.get("/api/workspace").json()["user"]["plan"] == "free"


def test_webhook_authentication_and_retry_after_provider_failure(
    client: TestClient, stripe: StripeFixture
) -> None:
    client.post("/api/billing/checkout")
    assert client.post("/api/billing/webhook", content=b"{}").status_code == 400
    assert (
        client.post(
            "/api/billing/webhook",
            content=b"{}",
            headers={"Stripe-Signature": f"t={int(time.time())},v1={'0' * 64}"},
        ).status_code
        == 400
    )
    assert signed_event(client, timestamp=int(time.time()) - 301).status_code == 400
    assert signed_event(client, timestamp=int(time.time()) + 301).status_code == 400
    stripe.fail = True
    response = signed_event(client)
    assert response.status_code == 502 and "private provider error" not in response.text
    with store.db() as c:
        assert c.execute("SELECT count(*) FROM billing_events").fetchone()[0] == 0
    stripe.fail = False
    stripe.subscriptions = [stripe.subscription()]
    assert signed_event(client).status_code == 200
    assert client.get("/api/workspace").json()["user"]["plan"] == "pro"


def test_price_mismatch_and_demo_cannot_checkout(
    client: TestClient, stripe: StripeFixture
) -> None:
    stripe.price = {**price(), "unit_amount": 2900}
    assert client.post("/api/billing/checkout").status_code == 503
    assert not any(path == "/v1/customers" for _, path, _ in stripe.calls)
    assert client.post("/api/demo").status_code == 200
    client.headers["X-CSRF-Token"] = client.get("/api/workspace").json()["csrf"]
    assert client.post("/api/billing/checkout").status_code == 403


def test_incomplete_checkout_and_pagination_fail_closed(
    client: TestClient, stripe: StripeFixture
) -> None:
    client.post("/api/billing/checkout")
    stripe.status = "complete"
    assert client.post("/api/billing/checkout").status_code == 409
    stripe.subscriptions = [stripe.subscription("incomplete")]
    assert client.post("/api/billing/checkout").status_code == 409
    stripe.paginated = True
    assert signed_event(client).status_code == 503
    assert client.get("/api/workspace").json()["user"]["plan"] == "free"
