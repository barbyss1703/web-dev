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
from shared.models import Event, BookingRequest, Booking, Flight, FlightCreateRequest, Payment

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
db = Database()
event_handler = EventHandler(
    db=db,
    consumer_group="BookingService_group",
    service_name="BookingService",
    redis_host=os.getenv("REDIS_HOST", "localhost"),
    redis_port=int(os.getenv("REDIS_PORT", "6379")),
    redis_db=int(os.getenv("REDIS_DB", "0"))
)

async def process_event(event):
    try:
        if event.event_type == "SeatReserved":
            booking_id = event.payload["booking_id"]
            sql = "UPDATE bookings SET status = 'SEAT_RESERVED' WHERE booking_id = $1"
            await db.execute_query(sql, booking_id)
            await event_handler.publish_event("BookingRequestedForPayment", {
                "booking_id": booking_id,
                "amount": 100.0  # Example amount
            })
        elif event.event_type == "PaymentProcessed":
            booking_id = event.payload["booking_id"]
            sql = "UPDATE bookings SET status = 'CONFIRMED' WHERE booking_id = $1"
            await db.execute_query(sql, booking_id)
            await event_handler.publish_event("BookingConfirmed", {"booking_id": booking_id})
        elif event.event_type in ["PaymentFailed", "SeatReservationFailed"]:
            booking_id = event.payload["booking_id"]
            sql = "UPDATE bookings SET status = 'FAILED' WHERE booking_id = $1"
            await db.execute_query(sql, booking_id)
            await event_handler.publish_event("BookingFailed", {"booking_id": booking_id})
    except Exception as e:
        logger.error(f"Error processing event {event.event_id}: {e}")

@app.get("/bookings", response_model=list[Booking])
async def get_bookings():
    sql = "SELECT * FROM bookings"
    result = await db.execute_to_model(Booking, sql)
    return result

@app.post("/bookings/create")
async def create_booking(request: BookingRequest):
    booking_id = None
    sql = """
        INSERT INTO bookings (flight_id, user_id, seat_number, status)
        VALUES ($1, $2, $3, 'PENDING')
        RETURNING booking_id
    """
    result = await db.execute_query(sql, request.flight_id, request.user_id, request.seat_number)
    booking_id = result[0]['booking_id']
    await event_handler.publish_event("BookingRequested", {
        "booking_id": booking_id,
        "flight_id": request.flight_id,
        "seat_number": request.seat_number
    })
    return {"booking_id": booking_id, "status": "PENDING"}

@app.get("/flights", response_model=list[Flight])
async def get_flights():
    result = await db.execute_to_model(Flight, "SELECT * FROM flights")
    return result

@app.post("/flights/create")
async def create_flight_endpoint(request: FlightCreateRequest):
    await event_handler.publish_event("FlightCreationRequested", {
        "total_seats": request.total_seats
    })
    return {"status": "REQUESTED"}

@app.get("/payments/{booking_id}", response_model=Payment)
async def get_payment(booking_id: int):
    sql = "SELECT payment_id, booking_id, amount, status FROM payments WHERE booking_id = $1"
    result = await db.execute_to_model(Payment, sql, booking_id)
    if not result:
        raise HTTPException(status_code=404, detail="Payment not found")
    return result[0]

@app.post("/payments/{booking_id}/create")
async def create_payment(booking_id: int, amount: float):
    # Check if booking exists
    sql = "SELECT booking_id FROM bookings WHERE booking_id = $1"
    booking = await db.execute_query(sql, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Publish event to request payment processing
    await event_handler.publish_event("BookingRequestedForPayment", {
        "booking_id": booking_id,
        "amount": amount
    })
    return {"booking_id": booking_id, "status": "PAYMENT_REQUESTED"}

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