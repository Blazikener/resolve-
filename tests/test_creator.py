"""Creator workflow, accounting and account-boundary regression tests."""

import csv
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app import creator_store as store
from app.creator import COOKIE, csv_cell


def signup(client: TestClient, email: str = "creator@example.com") -> None:
    response = client.post(
        "/api/signup",
        json={"email": email, "name": "Creator", "password": "a strong password"},
    )
    assert response.status_code == 201, response.text
    client.headers["X-CSRF-Token"] = client.get("/api/workspace").json()["csrf"]


def license_data() -> dict[str, object]:
    return {
        "brand": "Forma",
        "title": "Morning routine",
        "contact_email": "brand@example.com",
        "scope": "Meta paid ads, US",
        "starts_on": "2026-09-01",
        "expires_on": "2026-10-06",
        "renewal_fee_cents": 45001,
        "renewal_days": 30,
        "content_url": "https://example.com/video",
    }


def add_license(client: TestClient) -> str:
    response = client.post("/api/licenses", json=license_data())
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def proposal(client: TestClient, license_id: str) -> str:
    response = client.post(f"/api/licenses/{license_id}/propose")
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def approve(client: TestClient, renewal_id: str) -> None:
    response = client.post(
        f"/api/renewals/{renewal_id}/accept",
        json={
            "approval_note": "Confirmed by Jamie in email on Sep 30",
            "due_on": "2026-10-30",
        },
    )
    assert response.status_code == 200, response.text


def test_session_password_storage_csrf_and_logout(client: TestClient) -> None:
    assert client.get("/api/workspace").status_code == 401
    signup(client, "Creator@Example.com")
    workspace = client.get("/api/workspace").json()
    assert workspace["user"]["email"] == "creator@example.com"
    assert workspace["user"]["plan"] == "free"
    assert workspace["billing_available"] is False
    with store.db() as c:
        row = c.execute("SELECT * FROM users").fetchone()
        assert row["password"] != "a strong password"
        session = c.execute("SELECT hash FROM sessions").fetchone()
        assert session["hash"] != client.cookies[COOKIE]
    assert (
        client.post(
            "/api/licenses", json=license_data(), headers={"X-CSRF-Token": ""}
        ).status_code
        == 403
    )
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/workspace").status_code == 401
    assert (
        client.post(
            "/api/login",
            json={"email": "creator@example.com", "password": "incorrect password"},
        ).status_code
        == 401
    )
    login = client.post(
        "/api/login",
        json={"email": "creator@example.com", "password": "a strong password"},
    )
    assert login.status_code == 200
    assert "HttpOnly" in login.headers["set-cookie"]
    assert "SameSite=strict" in login.headers["set-cookie"]
    assert client.get("/api/workspace").json()["licenses"] == []


def test_password_whitespace_is_significant(client: TestClient) -> None:
    password = "  very long secret  "
    assert (
        client.post(
            "/api/signup",
            json={"name": "A", "email": "a@example.com", "password": password},
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/login", json={"email": "a@example.com", "password": password.strip()}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/login", json={"email": "a@example.com", "password": password}
        ).status_code
        == 200
    )


def test_tenant_isolation_across_reads_writes_and_exports(client: TestClient) -> None:
    signup(client)
    license_id = add_license(client)
    renewal_id = proposal(client, license_id)
    approve(client, renewal_id)
    payment_id = client.post(
        f"/api/renewals/{renewal_id}/payments",
        json={
            "amount_cents": 100,
            "reference": "bank",
            "idempotency_key": "first-payment-key",
        },
    ).json()["id"]
    signup(client, "second@example.com")
    assert client.get("/api/workspace").json()["licenses"] == []
    for path in (
        f"/api/licenses/{license_id}/packet",
        f"/api/renewals/{renewal_id}/draft",
    ):
        assert client.get(path).status_code == 404
    for path in (
        f"/api/licenses/{license_id}/propose",
        f"/api/renewals/{renewal_id}/decline",
        f"/api/payments/{payment_id}/reverse",
    ):
        assert client.post(path).status_code == 404
    assert (
        client.put(
            f"/api/licenses/{license_id}", json={**license_data(), "revision": 1}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/renewals/{renewal_id}/accept",
            json={"approval_note": "not mine", "due_on": "2026-10-30"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/renewals/{renewal_id}/payments",
            json={
                "amount_cents": 100,
                "reference": "bank",
                "idempotency_key": "second-payment-key",
            },
        ).status_code
        == 404
    )
    assert "Forma" not in client.get("/api/export").text


def test_end_to_end_accounting_idempotency_reversal_and_exports(
    client: TestClient,
) -> None:
    signup(client)
    license_id = add_license(client)
    renewal_id = proposal(client, license_id)
    assert proposal(client, license_id) == renewal_id
    renewal = client.get("/api/workspace").json()["renewals"][0]
    assert renewal["starts_on"] == "2026-10-07"
    assert renewal["expires_on"] == "2026-11-05"
    draft = client.get(f"/api/renewals/{renewal_id}/draft").json()
    assert "450.01" in draft["body"] and "Proposed" in draft["body"]
    first = {
        "amount_cents": 20000,
        "reference": "bank 100",
        "idempotency_key": "first-payment-key",
    }
    assert (
        client.post(f"/api/renewals/{renewal_id}/payments", json=first).status_code
        == 409
    )
    approve(client, renewal_id)
    assert (
        client.get("/api/workspace").json()["licenses"][0]["expires_on"] == "2026-11-05"
    )
    assert client.post(f"/api/renewals/{renewal_id}/decline").status_code == 409
    response = client.post(f"/api/renewals/{renewal_id}/payments", json=first)
    assert response.status_code == 201
    assert (
        client.post(f"/api/renewals/{renewal_id}/payments", json=first).json()["id"]
        == response.json()["id"]
    )
    assert (
        client.post(
            f"/api/renewals/{renewal_id}/payments",
            json={**first, "amount_cents": 20001},
        ).status_code
        == 409
    )
    draft = client.get(f"/api/renewals/{renewal_id}/draft").json()
    assert "250.01 outstanding" in draft["body"] and "My records show" in draft["body"]
    second = {
        "amount_cents": 25002,
        "reference": "bank 101",
        "idempotency_key": "second-payment-key",
    }
    assert (
        client.post(f"/api/renewals/{renewal_id}/payments", json=second).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/renewals/{renewal_id}/payments",
            json={**second, "amount_cents": 25001},
        ).status_code
        == 201
    )
    assert client.get(f"/api/renewals/{renewal_id}/draft").status_code == 409
    packet = client.get(f"/api/licenses/{license_id}/packet")
    assert "recorded received USD 450.01" in packet.text
    assert "not independently verified" in packet.text
    rows = list(csv.DictReader(io.StringIO(client.get("/api/export").text)))
    assert "450.01" in rows[0].values()
    payment_id = response.json()["id"]
    assert client.post(f"/api/payments/{payment_id}/reverse").json()["reversed"] is True
    assert client.post(f"/api/payments/{payment_id}/reverse").json()["reversed"] is True
    assert (
        "200.00 outstanding"
        in client.get(f"/api/renewals/{renewal_id}/draft").json()["body"]
    )
    assert (
        client.post(f"/api/renewals/{renewal_id}/payments", json=first).json()[
            "reversed"
        ]
        is True
    )
    assert len(client.get("/api/workspace").json()["payments"]) == 2


def test_concurrent_payments_cannot_overpay(client: TestClient) -> None:
    signup(client)
    renewal_id = proposal(client, add_license(client))
    approve(client, renewal_id)

    def pay(index: int) -> int:
        return client.post(
            f"/api/renewals/{renewal_id}/payments",
            json={
                "amount_cents": 30000,
                "reference": "bank",
                "idempotency_key": f"concurrent-key-{index:04d}",
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(pay, (1, 2))) == [201, 422]
    assert len(client.get("/api/workspace").json()["payments"]) == 1


def test_revision_conflicts_and_old_draft_terms(client: TestClient) -> None:
    signup(client)
    license_id = add_license(client)
    renewal_id = proposal(client, license_id)
    changed = {**license_data(), "renewal_fee_cents": 60000, "revision": 1}
    assert client.put(f"/api/licenses/{license_id}", json=changed).status_code == 200
    assert client.put(f"/api/licenses/{license_id}", json=changed).status_code == 409
    assert client.post(f"/api/licenses/{license_id}/propose").status_code == 409
    assert (
        client.post(
            f"/api/renewals/{renewal_id}/accept",
            json={"approval_note": "email approval", "due_on": "2026-10-30"},
        ).status_code
        == 409
    )
    assert client.post(f"/api/renewals/{renewal_id}/decline").status_code == 200
    fresh = proposal(client, license_id)
    assert fresh != renewal_id
    assert "600.00" in client.get(f"/api/renewals/{fresh}/draft").json()["body"]


def test_free_limit_archive_and_restore(client: TestClient) -> None:
    signup(client)
    ids = [add_license(client) for _ in range(3)]
    assert client.post("/api/licenses", json=license_data()).status_code == 402
    assert (
        client.put(
            f"/api/licenses/{ids[0]}",
            json={**license_data(), "revision": 1, "archived": True},
        ).status_code
        == 200
    )
    assert client.post(f"/api/licenses/{ids[0]}/propose").status_code == 409
    add_license(client)
    assert (
        client.put(
            f"/api/licenses/{ids[0]}",
            json={**license_data(), "revision": 2, "archived": False},
        ).status_code
        == 402
    )


def test_expired_license_does_not_imply_retroactive_rights(client: TestClient) -> None:
    signup(client)
    license_id = client.post(
        "/api/licenses", json={**license_data(), "expires_on": "2026-09-20"}
    ).json()["id"]
    renewal_id = proposal(client, license_id)
    assert (
        client.get("/api/workspace").json()["renewals"][0]["starts_on"] == "2026-09-30"
    )
    approve(client, renewal_id)
    assert (
        client.get("/api/workspace").json()["licenses"][0]["starts_on"] == "2026-09-30"
    )
    assert (
        "2026-09-01 to 2026-09-20"
        in client.get(f"/api/licenses/{license_id}/packet").text
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"renewal_fee_cents": 0},
        {"renewal_fee_cents": 10.5},
        {"renewal_fee_cents": "200"},
        {"renewal_fee_cents": True},
        {"renewal_days": 0},
        {"renewal_days": 731},
        {"expires_on": "2026-08-01"},
        {"starts_on": "1999-01-01"},
        {"contract_url": "javascript:alert(1)"},
        {"content_url": "https://example.com\nmalicious"},
        {"contact_email": "x@example.com\r\nBcc:evil@example.com"},
        {"brand": "  "},
        {"user_id": "other-user"},
    ],
)
def test_input_validation(client: TestClient, changes: dict[str, object]) -> None:
    signup(client)
    assert (
        client.post("/api/licenses", json={**license_data(), **changes}).status_code
        == 422
    )


def test_formula_export_and_html_payload_remain_data(client: TestClient) -> None:
    signup(client)
    response = client.post(
        "/api/licenses",
        json={
            **license_data(),
            "brand": '=HYPERLINK("https://evil.example")',
            "title": "<img src=x onerror=alert(1)>",
        },
    )
    proposal(client, response.json()["id"])
    row = list(csv.reader(io.StringIO(client.get("/api/export").text)))[1]
    assert row[0].startswith("'=")
    assert row[1] == "<img src=x onerror=alert(1)>"
    for cell in ("=formula", " +formula", "\tcommand", "@formula", "\r=cmd"):
        assert csv_cell(cell).startswith("'")


def test_demo_is_private_and_disposable(client: TestClient) -> None:
    assert client.post("/api/demo").status_code == 200
    first = client.get("/api/workspace").json()
    assert len(first["licenses"]) == 3 and first["user"]["demo"]
    assert client.post("/api/demo").status_code == 200
    second = client.get("/api/workspace").json()
    assert first["user"]["id"] != second["user"]["id"]
    assert first["licenses"][0]["id"] != second["licenses"][0]["id"]
    client.headers["X-CSRF-Token"] = second["csrf"]
    assert client.post("/api/logout").status_code == 200
    with store.db() as c:
        assert (
            c.execute(
                "SELECT count(*) FROM records WHERE user_id=?", (second["user"]["id"],)
            ).fetchone()[0]
            == 0
        )


def test_security_headers_origin_body_size_and_billing_off(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/").status_code == 200
    for path in ("/app", "/assets/creator.css", "/assets/creator.js", "/health"):
        assert client.get(path).status_code == 200
    headers = client.get("/").headers
    assert "script-src 'self'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert (
        client.post("/api/demo", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert client.post("/api/demo", content=b"x" * 131073).status_code == 413
    signup(client)
    assert client.post("/api/billing/checkout").status_code == 503
    monkeypatch.setenv("RESOLVE_PUBLIC_URL", "https://resolve.example")
    assert "max-age" in client.get("/").headers["strict-transport-security"]
    response = client.post(
        "/api/login",
        json={"email": "creator@example.com", "password": "a strong password"},
    )
    assert "; Secure" in response.headers["set-cookie"]


def test_restart_retains_private_records(client: TestClient) -> None:
    signup(client)
    license_id = add_license(client)
    store.initialize()
    assert client.get("/api/workspace").json()["licenses"][0]["id"] == license_id


def test_throttle_survives_rejection(client: TestClient) -> None:
    for _ in range(15):
        assert (
            client.post(
                "/api/login",
                json={"email": "nobody@example.com", "password": "wrong password"},
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/login",
            json={"email": "nobody@example.com", "password": "wrong password"},
        ).status_code
        == 429
    )
    assert (
        client.post(
            "/api/login",
            json={"email": "nobody@example.com", "password": "wrong password"},
        ).status_code
        == 429
    )


def test_renewal_cannot_overflow_supported_calendar(client: TestClient) -> None:
    signup(client)
    license_id = client.post(
        "/api/licenses", json={**license_data(), "expires_on": "2100-12-31"}
    ).json()["id"]
    assert client.post(f"/api/licenses/{license_id}/propose").status_code == 422
    renewal_id = proposal(client, add_license(client))
    assert (
        client.post(
            f"/api/renewals/{renewal_id}/accept",
            json={
                "approval_note": "approved",
                "due_on": (store.today() - timedelta(days=1)).isoformat(),
            },
        ).status_code
        == 422
    )
