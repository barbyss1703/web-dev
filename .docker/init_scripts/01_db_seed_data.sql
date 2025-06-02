\c flightproj;

INSERT INTO flights (flight_id, total_seats, available_seats)
VALUES (1, 100, 100)
ON CONFLICT DO NOTHING