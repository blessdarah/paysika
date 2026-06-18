from pydantic import BaseModel, Field


class PaymentWebhookPayload(BaseModel):
    event_id: str
    event_type: str
    reference_id: str
    provider_reference: str
    amount: str
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    status: str
    timestamp: str
    metadata: dict = Field(default_factory=dict)
