import os
import uvicorn
import asyncio
import redis
import sys
import json
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, PositiveInt
from uuid import uuid4
from shared.event_handler import EventHandler
from shared.database import Database
from shared.models import Event, Flight, FlightCreateRequest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
db = Database()
event_handler = EventHandler(
    db=db,
    consumer_group="FlightService_group",
    service_name="FlightService",
    redis_host=os.getenv("REDIS_HOST", "localhost"),
    redis_port=int(os.getenv("REDIS_PORT", "6379")),
    redis_db=int(os.getenv("REDIS_DB", "0"))
)

async def process_event(event):
    try:
        logger.debug(f"Recieved event {event.event_type}")
        if event.event_type == "BookingRequested":
            booking_id = event.payload["booking_id"]
            flight_id = event.payload["flight_id"]
            seat_number = event.payload["seat_number"]
            # Check seat availability
            sql = "SELECT available_seats FROM flights WHERE flight_id = $1 FOR UPDATE"
            result = await db.execute_query(sql, flight_id)
            if not result or result[0]["available_seats"] <= 0:
                await event_handler.publish_event("SeatReservationFailed", {"booking_id": booking_id})
                return
            # Reserve seat
            sql1 = """
                UPDATE flights SET available_seats = available_seats - 1 WHERE flight_id = $1;
            """
            await db.execute_query(sql1, flight_id)
            sql2 = """
                INSERT INTO reservations (booking_id, flight_id, seat_number)
                VALUES ($1, $2, $3);
            """
            await db.execute_query(sql2, booking_id, flight_id, seat_number)
            await event_handler.publish_event("SeatReserved", {"booking_id": booking_id, "flight_id": flight_id})
        elif event.event_type == "BookingFailed":
            booking_id = event.payload["booking_id"]
            # Free reserved seat
            sql = "SELECT flight_id FROM reservations WHERE booking_id = $1"
            result = await db.execute_query(sql, booking_id)
            if result:
                flight_id = result[0]["flight_id"]
                sql1 = """
                    UPDATE flights SET available_seats = available_seats + 1 WHERE flight_id = $1;
                """
                await db.execute_query(sql1, flight_id)
                sql2 = """
                    DELETE FROM reservations WHERE booking_id = $1;
                """
                await db.execute_query(sql2, booking_id)
        elif event.event_type == "FlightCreationRequested":
            total_seats = event.payload["total_seats"]
            available_seats = total_seats
            sql = """
                INSERT INTO flights (total_seats, available_seats)
                VALUES ($1, $2)
            """
            await db.execute_query(sql, total_seats, available_seats)
    except Exception as e:
        logger.error(f"Error processing event {event.event_id}: {e}")

@app.get("/flights/{flight_id}", response_model=Flight)
async def get_flight(flight_id: PositiveInt):
    sql = "SELECT flight_id, total_seats, available_seats FROM flights WHERE flight_id = $1"
    result = await db.execute_to_model(Flight, sql, flight_id)
    if not result:
        raise HTTPException(status_code=404, detail="Flight not found")
    return result[0]

@app.post("/flights")
async def create_flight(request: FlightCreateRequest):
    sql = """
        INSERT INTO flights (total_seats, available_seats)
        VALUES ($1, $2)
        RETURNING flight_id, total_seats, available_seats
    """
    result = await db.execute_to_model(Flight, sql, request.total_seats, request.total_seats)
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