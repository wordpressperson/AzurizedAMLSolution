import json
import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from azure.servicebus import ServiceBusMessage
from fastapi import FastAPI, HTTPException, status, Query
from pydantic import BaseModel
from azure.servicebus.aio import ServiceBusClient

from alerts import AlertManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AML Alert Manager API",
    version="1.0.0",
    description="Manages AML alerts, deduplication, and SAR narrative generation"
)

# Global variables
sb_client = None
alert_manager = None
topic_name = "aml-events"
subscription_name = "alert-manager"

class Alert(BaseModel):
    alert_id: str
    txn_id: str
    customer_id: str
    risk_score: float
    status: str
    alert_type: str
    created_at: datetime
    updated_at: datetime
    sar_narrative: Optional[str] = None
    investigation_notes: Optional[str] = None
    assigned_to: Optional[str] = None

class AlertUpdate(BaseModel):
    status: Optional[str] = None
    investigation_notes: Optional[str] = None
    assigned_to: Optional[str] = None

class AlertsResponse(BaseModel):
    alerts: List[Alert]
    total: int
    limit: int
    offset: int

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime

@app.on_event("startup")
async def startup_event():
    """Initialize Service Bus client and alert manager"""
    global sb_client, alert_manager
    try:
        alert_manager = AlertManager()

        connection_str = os.getenv("SERVICE_BUS_CONNECTION_STR")
        if not connection_str:
            raise ValueError("SERVICE_BUS_CONNECTION_STR environment variable not set")
        sb_client = ServiceBusClient.from_connection_string(connection_str)
        logger.info("Service Bus client created")

        # Start consuming messages
        asyncio.create_task(consume_messages())

        logger.info("Alert Manager service started successfully")
    except Exception as e:
        logger.error(f"Failed to start Alert Manager service: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    global sb_client
    if sb_client:
        await sb_client.close()
        logger.info("Service Bus client closed")

async def process_message(message: ServiceBusMessage, receiver):
    """Process a single message from Service Bus – expecting Scored events"""
    try:
        body = json.loads(str(message))
        event_type = body.get("event_type")
        data = body.get("data", {})

        if event_type == "Scored":
            # Create alert from scored transaction
            alert = await alert_manager.process_scored_transaction(data)
            if alert:
                logger.info(f"Created alert {alert['alert_id']} for transaction {alert['txn_id']}")

        await receiver.complete_message(message)
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await receiver.dead_letter_message(message, reason="Processing error", error_description=str(e))

async def consume_messages():
    if not sb_client:
        logger.error("Service Bus client not available")
        return
    async with sb_client:
        receiver = sb_client.get_subscription_receiver(topic_name, subscription_name, max_wait_time=5)
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

@app.get("/alerts", response_model=AlertsResponse)
async def get_alerts(
    status: Optional[str] = Query(None),
    risk_threshold: Optional[float] = Query(None),
    limit: int = Query(100),
    offset: int = Query(0)
):
    try:
        alerts = await alert_manager.get_alerts(
            status=status, risk_threshold=risk_threshold, limit=limit, offset=offset
        )
        total = await alert_manager.count_alerts(status=status, risk_threshold=risk_threshold)
        return AlertsResponse(alerts=alerts, total=total, limit=limit, offset=offset)
    except Exception as e:
        logger.error(f"Error retrieving alerts: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving alerts")

@app.get("/alerts/{alert_id}", response_model=Alert)
async def get_alert(alert_id: str):
    try:
        alert = await alert_manager.get_alert_by_id(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        return Alert(**alert)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving alert")

@app.patch("/alerts/{alert_id}", response_model=Alert)
async def update_alert(alert_id: str, update: AlertUpdate):
    try:
        updated = await alert_manager.update_alert(alert_id, update.dict(exclude_unset=True))
        if not updated:
            raise HTTPException(status_code=404, detail="Alert not found")
        return Alert(**updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail="Error updating alert")

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy", timestamp=datetime.utcnow())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
