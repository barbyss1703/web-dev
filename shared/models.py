from pydantic import BaseModel
from uuid import UUID

class BookingRequest(BaseModel):
    flight_id: int
    user_id: str
    seat_number: str

class Booking(BaseModel):
    booking_id: int
    flight_id: int
    user_id: str
    seat_number: str
    status: str

class Flight(BaseModel):
    flight_id: int
    total_seats: int
    available_seats: int

class Payment(BaseModel):
    payment_id: int
    booking_id: int
    amount: float
    status: str

class Event(BaseModel):
    event_id: str
    event_type: str
    payload: dict

class FlightCreateRequest(BaseModel):
    total_seats: int