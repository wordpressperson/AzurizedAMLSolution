from pydantic import BaseModel
from typing import Dict, Any

class Transaction(BaseModel):
    txn_id: str
    account_id: str
    customer_id: str
    amount: float
    currency: str
    timestamp: str
    counterparty_country: str = "US"
    # add any other fields you need
