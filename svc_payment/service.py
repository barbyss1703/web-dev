import os
import uvicorn
import asyncio
import redis
import sys
import json
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from shared.event_handler import EventHandler
from shared.database import Database
from shared.models import Event, Payment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
db = Database()
event_handler = EventHandler(
    db=db,
    consumer_group="PaymentService_group",
    service_name="PaymentService",
    redis_host=os.getenv("REDIS_HOST", "localhost"),
    redis_port=int(os.getenv("REDIS_PORT", "6379")),
    redis_db=int(os.getenv("REDIS_DB", "0"))
)

async def process_event(event):
    try:
        if event.event_type == "BookingRequestedForPayment":
            booking_id = event.payload["booking_id"]
            amount = event.payload["amount"]
            # Simulate payment processing (success for simplicity)
            success = True  # In real scenarios, integrate with a payment gateway
            status = "SUCCESS" if success else "FAILED"
            # Save payment
            sql = """
                INSERT INTO payments (booking_id, amount, status)
                VALUES ($1, $2, $3)
            """
            await db.execute_query(sql, booking_id, amount, status)
            # Publish appropriate event
            if success:
                await event_handler.publish_event("PaymentProcessed", {
                    "booking_id": booking_id,
                })
            else:
                await event_handler.publish_event("PaymentFailed", {"booking_id": booking_id})
    except Exception as e:
        logger.error(f"Error processing event {event.event_id}: {e}")

@app.get("/payments/{booking_id}", response_model=Payment)
async def get_payment(booking_id: str):
    sql = "SELECT payment_id, booking_id, amount, status FROM payments WHERE booking_id = $1"
    result = await db.execute_to_model(Payment, sql, booking_id)
    if not result:
        raise HTTPException(status_code=404, detail="Payment not found")
    return result[0]

@app.on_event("startup")
async def startup_event():
    await db.connect()
    asyncio.create_task(event_handler.consume_events(process_event))

@app.on_event("shutdown")
async def shutdown_event():
    await db.disconnect()
    event_handler.r.close()

if __name__ == "__main__":
    host, port = sys.argv[1].split(":")
    uvicorn.run("service:app", host=host, port=int(port), reload=True, log_level="debug")