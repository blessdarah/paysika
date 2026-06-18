from pydantic import BaseModel, Field


class PaymentWebhookPayload(BaseModel):
    event_type: str
    transaction_id: str
    amount: str
    currency: str
    status: str
    timestamp: str
    metadata: dict = Field(default_factory=dict)
