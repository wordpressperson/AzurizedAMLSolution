import json
import uuid
import os
from datetime import datetime, date
from typing import List, Dict, Any
import asyncio
import logging

from fastapi import FastAPI, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage

from models import Account, Customer, Transaction
from data_processor import DataProcessor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AML Ingestion API",
    version="1.0.0",
    description="Accepts batch uploads of accounts, customers, and transactions data"
)

# Global Service Bus client
sb_client = None
topic_name = "aml-events"

# Initialize data processor
data_processor = DataProcessor()

def serialize_datetime(obj):
    """Convert datetime objects to JSON serializable format"""
    if isinstance(obj, datetime):
        return obj.isoformat() + "Z"
    elif isinstance(obj, date):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: serialize_datetime(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetime(item) for item in obj]
    return obj

class BatchResponse(BaseModel):
    message: str
    batch_id: str
    records_processed: int

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime

@app.on_event("startup")
async def startup_event():
    """Initialize Service Bus client on startup"""
    global sb_client
    try:
        connection_str = os.getenv("SERVICE_BUS_CONNECTION_STR")
        if not connection_str:
            raise ValueError("SERVICE_BUS_CONNECTION_STR environment variable not set")
        sb_client = ServiceBusClient.from_connection_string(connection_str)
        logger.info("Service Bus client created successfully")
    except Exception as e:
        logger.error(f"Failed to create Service Bus client: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Close Service Bus connection on shutdown"""
    global sb_client
    if sb_client:
        await sb_client.close()
        logger.info("Service Bus client closed")

async def publish_batch_events(event_type: str, items: List[Dict], batch_id: str, sender):
    """
    Publish multiple events of the same type using a single sender.
    """
    for item in items:
        message_body = {
            "event_type": event_type,
            "batch_id": batch_id,
            "data": item,
            "timestamp": datetime.utcnow().isoformat()
        }
        message = ServiceBusMessage(
            body=json.dumps(message_body),
            content_type="application/json",
            application_properties={
                "event_type": event_type,
                "batch_id": batch_id
            }
        )
        await sender.send_messages(message)
        logger.debug(f"Published {event_type} for batch {batch_id}")

@app.post("/batch", response_model=BatchResponse, status_code=status.HTTP_201_CREATED)
async def upload_batch(
    accounts: UploadFile = File(...),
    customers: UploadFile = File(...),
    transactions: UploadFile = File(...)
):
    """Upload batch data files and publish events to Service Bus"""
    batch_id = str(uuid.uuid4())
    total_records = 0
    
    try:
        # Read file contents
        accounts_content = await accounts.read()
        customers_content = await customers.read()
        transactions_content = await transactions.read()
        
        # Process and enrich data using data processor
        enriched_accounts, enriched_customers, enriched_transactions = await data_processor.process_batch_files(
            accounts_content, customers_content, transactions_content
        )
        
        # Validate enriched data with Pydantic models
        validated_accounts = []
        for account_data in enriched_accounts:
            try:
                account = Account(**account_data)
                validated_accounts.append(account.dict() if hasattr(account, 'dict') else account)
            except ValidationError as e:
                logger.warning(f"Account validation warning: {e}")
                validated_accounts.append(account_data)
        
        validated_customers = []
        for customer_data in enriched_customers:
            try:
                customer = Customer(**customer_data)
                validated_customers.append(customer.dict() if hasattr(customer, 'dict') else customer)
            except ValidationError as e:
                logger.warning(f"Customer validation warning: {e}")
                validated_customers.append(customer_data)
        
        validated_transactions = []
        for transaction_data in enriched_transactions:
            try:
                transaction = Transaction(**transaction_data)
                validated_transactions.append(transaction.dict() if hasattr(transaction, 'dict') else transaction)
            except ValidationError as e:
                logger.warning(f"Transaction validation warning: {e}")
                validated_transactions.append(transaction_data)
        
        # Serialize datetime fields
        validated_accounts = [serialize_datetime(acc) for acc in validated_accounts]
        validated_customers = [serialize_datetime(cust) for cust in validated_customers]
        validated_transactions = [serialize_datetime(txn) for txn in validated_transactions]
        
        total_records = len(validated_accounts) + len(validated_customers) + len(validated_transactions)
        
        # Use a single sender for the whole batch
        async with sb_client.get_topic_sender(topic_name) as sender:
            await publish_batch_events("IngestedAccount", validated_accounts, batch_id, sender)
            await publish_batch_events("IngestedCustomer", validated_customers, batch_id, sender)
            await publish_batch_events("IngestedTransaction", validated_transactions, batch_id, sender)
        
        logger.info(f"Processed batch {batch_id} with {total_records} records")
        
        return BatchResponse(
            message="Batch uploaded successfully",
            batch_id=batch_id,
            records_processed=total_records
        )
        
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON format in uploaded files"
        )
    except Exception as e:
        logger.error(f"Error processing batch: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error processing batch: {str(e)}"
        )

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow()
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
