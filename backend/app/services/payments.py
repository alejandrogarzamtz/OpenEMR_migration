from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4


@dataclass(frozen=True)
class ProcessorResult:
    succeeded: bool
    reference: str | None = None
    failure_code: str | None = None


class PaymentProcessor:
    def charge(self, *, amount: Decimal, currency: str, token: str, idempotency_key: str) -> ProcessorResult:
        raise NotImplementedError


class DisabledProcessor(PaymentProcessor):
    def charge(self, *, amount: Decimal, currency: str, token: str, idempotency_key: str) -> ProcessorResult:
        return ProcessorResult(False, failure_code="processor_not_configured")


class TestProcessor(PaymentProcessor):
    """Deterministic contract adapter used only by automated tests."""

    def charge(self, *, amount: Decimal, currency: str, token: str, idempotency_key: str) -> ProcessorResult:
        if token == "tok_test_declined":
            return ProcessorResult(False, failure_code="card_declined")
        if not token.startswith("tok_test_"):
            return ProcessorResult(False, failure_code="invalid_test_token")
        return ProcessorResult(True, reference=f"test_{uuid4()}")


def payment_processor(name: str, deployment_environment: str) -> PaymentProcessor:
    if name == "test" and deployment_environment == "test":
        return TestProcessor()
    return DisabledProcessor()
