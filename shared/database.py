import os
import asyncpg
from asyncpg.exceptions import PostgresError
from typing import Type, List
from pydantic import BaseModel, conlist

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        try:
            self.pool = await asyncpg.create_pool(os.getenv("POSTGRES_CONN_STRING"))
        except Exception as e:
            raise ConnectionError(f"Error connecting to database: {e}")

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def execute_query(self, sql, *parameters):
        if not self.pool:
            raise RuntimeError("Database connection pool is not initialized")
        try:
            response = await self.pool.fetch(sql, *parameters)
            return [dict(row) for row in response]
        except PostgresError as e:
            print(f"Postgres error: {e}")
            raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise

    async def execute_to_model(self, model: Type[BaseModel], sql: str, *parameters) -> List[BaseModel]:
        result = await self.execute_query(sql, *parameters)
        return [model(**item) for item in result]