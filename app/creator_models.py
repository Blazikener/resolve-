"""Validated records for the creator licensing pilot."""

import re
from datetime import date
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Credentials(Record):
    email: str = Field(min_length=3, max_length=254)
    password: Annotated[str, StringConstraints(strip_whitespace=False)] = Field(
        min_length=10, max_length=128
    )

    @field_validator("email")
    @classmethod
    def email_address(cls, value: str) -> str:
        if not re.fullmatch(
            r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+", value
        ):
            raise ValueError("Enter a valid email address")
        return value.lower()


class Signup(Credentials):
    name: str = Field(min_length=1, max_length=80)


class User(Record):
    id: str
    email: str
    name: str
    demo: bool = False
    plan: str = "free"
    customer_id: str = ""
    subscription_id: str = ""


class LicenseInput(Record):
    brand: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=160)
    contact_email: str = Field(min_length=3, max_length=254)
    scope: str = Field(min_length=1, max_length=500)
    starts_on: date
    expires_on: date
    renewal_fee_cents: int = Field(strict=True, gt=0, le=100_000_000)
    renewal_days: int = Field(strict=True, ge=1, le=730)
    contract_url: str = Field(default="", max_length=2000)
    content_url: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=3000)
    archived: bool = False

    @field_validator("contact_email")
    @classmethod
    def contact(cls, value: str) -> str:
        return Credentials.email_address(value)

    @field_validator("contract_url", "content_url")
    @classmethod
    def web_link(cls, value: str) -> str:
        if value and (
            not re.match(r"^https?://[^\s/]+", value) or any(ord(c) < 32 for c in value)
        ):
            raise ValueError("Use a full http or https link")
        return value

    @model_validator(mode="after")
    def dates(self) -> Self:
        if self.expires_on < self.starts_on:
            raise ValueError("Expiry must be on or after the start date")
        if self.expires_on.year > 2100 or self.starts_on.year < 2000:
            raise ValueError("Dates must fall between 2000 and 2100")
        return self


class License(LicenseInput):
    id: str
    revision: int = 1


class LicenseEdit(LicenseInput):
    revision: int = Field(ge=1)


class Renewal(Record):
    id: str
    license_id: str
    license_revision: int
    brand: str
    title: str
    contact_email: str
    scope: str
    starts_on: date
    expires_on: date
    fee_cents: int
    contract_url: str = ""
    content_url: str = ""
    status: Literal["draft", "accepted", "declined"] = "draft"
    due_on: date | None = None
    approval_note: str = ""
    created_at: str


class Acceptance(Record):
    approval_note: str = Field(min_length=5, max_length=2000)
    due_on: date


class PaymentInput(Record):
    amount_cents: int = Field(strict=True, gt=0, le=100_000_000)
    reference: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{16,80}$")


class Payment(Record):
    id: str
    renewal_id: str
    amount_cents: int
    reference: str
    idempotency_key: str
    created_at: str
    reversed: bool = False


class Activity(Record):
    id: str
    license_id: str
    text: str
    created_at: str


class Workspace(Record):
    user: User
    csrf: str
    today: date
    licenses: list[License]
    renewals: list[Renewal]
    payments: list[Payment]
    activity: list[Activity]
    billing_available: bool
