import os
import json
import asyncio
import logging
from datetime import datetime
from fastapi import FastAPI
from pydantic import BaseModel
from azure.servicebus.aio import ServiceBusClient
from azure.servicebus import ServiceBusMessage

from features import extract_features

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Feature Engineering Service", version="1.0.0")

# Service Bus configuration
connection_str = os.getenv("SERVICE_BUS_CONNECTION_STR")
topic_name = "aml-events"
subscription_name = "feature-engine"

sb_client = None

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime

@app.on_event("startup")
async def startup_event():
    global sb_client
    try:
        if not connection_str:
            raise ValueError("SERVICE_BUS_CONNECTION_STR not set")
        sb_client = ServiceBusClient.from_connection_string(connection_str)
        logger.info("Service Bus client created")
        asyncio.create_task(consume_messages())
    except Exception as e:
        logger.error(f"Failed to initialize: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    global sb_client
    if sb_client:
        await sb_client.close()

async def publish_event(event_type: str, data: dict, batch_id: str = None):
    """Publish an event to the Service Bus topic"""
    if not sb_client:
        logger.error("Service Bus client not available")
        return
    try:
        message_body = {
            "event_type": event_type,
            "batch_id": batch_id,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        }
        message = ServiceBusMessage(
            body=json.dumps(message_body),
            content_type="application/json",
            application_properties={"event_type": event_type}
        )
        async with sb_client.get_topic_sender(topic_name) as sender:
            await sender.send_messages(message)
        logger.debug(f"Published {event_type}")
    except Exception as e:
        logger.error(f"Failed to publish: {e}")

async def process_message(message: ServiceBusMessage, receiver):
    try:
        body = json.loads(str(message))
        event_type = body.get("event_type")
        batch_id = body.get("batch_id")
        data = body.get("data")

        logger.info(f"Received {event_type} for batch {batch_id}")

        if event_type == "IngestedTransaction":
            # Extract features using empty stores (for demo simplicity)
            features = await extract_features(
                transaction=data,
                transaction_store={},
                customer_store={},
                account_store={}
            )
            logger.info(f"Extracted {len(features)} features for transaction {data['txn_id']}")

            # Publish FeaturesReady event for risk-scorer
            await publish_event(
                "FeaturesReady",
                {"txn_id": data["txn_id"], "features": features},
                batch_id
            )

        # Complete the message
        await receiver.complete_message(message)

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await receiver.dead_letter_message(message, reason="Processing error", error_description=str(e))

async def consume_messages():
    if not sb_client:
        logger.error("Service Bus client not available")
        return
    async with sb_client:
        receiver = sb_client.get_subscription_receiver(
            topic_name, subscription_name, max_wait_time=5
        )
        async with receiver:
            logger.info(f"Listening on subscription '{subscription_name}'...")
            while True:
                try:
                    msgs = await receiver.receive_messages(max_message_count=10, max_wait_time=5)
                    for msg in msgs:
                        await process_message(msg, receiver)
                except Exception as e:
                    logger.error(f"Error in receive loop: {e}")
                    await asyncio.sleep(5)

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy", timestamp=datetime.utcnow())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
