# event_handler.py
import asyncio
import json
import logging
import redis
import os
from uuid import uuid4
from typing import Dict, Any, Optional
from shared.models import Event
from shared.database import Database

logger = logging.getLogger(__name__)

class EventHandler:
    def __init__(
        self,
        db: Database,
        consumer_group: str = "Service_group",
        service_name: str = "Service",
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0
    ):
        self.db = db
        self.consumer_group = consumer_group
        self.service_name = service_name
        
        # Initialize Redis connection
        self.r = redis.Redis(
            connection_pool=redis.ConnectionPool(
                host=redis_host,
                port=redis_port,
                db=redis_db
            )
        )

    async def publish_event(self, event_type: str, payload: Dict[str, Any]) -> str:
        event_id = str(uuid4())
        event = Event(event_id=event_id, event_type=event_type, payload=payload)
        
        # Save to outbox
        sql = """
            INSERT INTO outbox (event_id, event_type, payload)
            VALUES ($1, $2, $3)
        """
        await self.db.execute_query(sql, event_id, event_type, json.dumps(event.dict()))
        
        # Publish to Redis stream
        self.r.xadd("booking_stream", {
            "event_id": event_id,
            "event_type": event_type,
            "payload": event.json()
        })
        logger.info(f"Published event {event_type} with ID {event_id}")
        return event_id

    async def consume_events(self, process_callback):
        # Create consumer group if it doesn't exist
        try:
            self.r.xgroup_create(
                "booking_stream",
                self.consumer_group,
                id="0",
                mkstream=True
            )
        except redis.RedisError as e:
            if "BUSYGROUP" not in str(e):
                logger.error(f"Failed to create consumer group: {e}")
                raise

        while True:
            try:
                # Read events from Redis stream
                events = self.r.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.service_name,
                    streams={"booking_stream": ">"},
                    count=1,
                    block=1000
                )
                
                if not events:
                    await asyncio.sleep(0.1)
                    continue
                    
                for stream, messages in events:
                    for message_id, message in messages:
                        try:
                            logger.debug(f"Received raw message: {message}")
                            
                            # Ensure message has required fields
                            if b'payload' not in message and 'payload' not in message:
                                logger.error(f"Message missing payload field: {message}")
                                self.r.xack("booking_stream", self.consumer_group, message_id)
                                continue
                                
                            # Get payload from message
                            payload_key = b'payload' if b'payload' in message else 'payload'
                            payload_value = message[payload_key]
                            
                            # Decode payload if it's bytes
                            if isinstance(payload_value, bytes):
                                try:
                                    payload_str = payload_value.decode('utf-8')
                                except UnicodeDecodeError as e:
                                    logger.error(f"Failed to decode payload: {e}")
                                    self.r.xack("booking_stream", self.consumer_group, message_id)
                                    continue
                            else:
                                payload_str = payload_value
                            
                            # Parse payload JSON
                            try:
                                payload_data = json.loads(payload_str)
                            except json.JSONDecodeError as e:
                                logger.error(f"Invalid JSON in payload: {payload_str}, error: {e}")
                                self.r.xack("booking_stream", self.consumer_group, message_id)
                                continue
                            
                            # Validate and create Event
                            try:
                                event = Event(**payload_data)
                            except Exception as e:
                                logger.error(f"Failed to validate event: {payload_data}, error: {e}")
                                self.r.xack("booking_stream", self.consumer_group, message_id)
                                continue
                            
                            # Save to inbox
                            sql = """
                                INSERT INTO inbox (event_id, event_type, payload)
                                VALUES ($1, $2, $3)
                                ON CONFLICT (event_id) DO NOTHING
                            """
                            await self.db.execute_query(sql, event.event_id, event.event_type, json.dumps(event.dict()))
                            
                            # Process event using the callback
                            try:
                                await process_callback(event)
                            except Exception as e:
                                logger.error(f"Error in process_callback: {e}")
                                continue
                                
                            # Acknowledge message
                            self.r.xack("booking_stream", self.consumer_group, message_id)
                            
                        except Exception as e:
                            logger.error(f"Error processing message {message_id}: {e}")
                            continue
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Error in consume_events loop: {e}")
                await asyncio.sleep(1)