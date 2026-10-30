import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from typing import Optional

import psycopg
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Security
from fastapi.security import APIKeyHeader
from psycopg import errors, sql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel, ConfigDict, create_model

API_KEY = os.environ["API_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: Optional[str] = Security(api_key_header)) -> None:
    if not key or not secrets.compare_digest(key, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = AsyncConnectionPool(
        DATABASE_URL, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=False
    )
    await pool.open()
    app.state.pool = pool
    yield
    await pool.close()


app = FastAPI(title="CRM API", lifespan=lifespan)


# ---- models (mirror db/init/01_schema.sql; inserted_at is DB-managed, read-only) ----

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SalesPersonIn(StrictModel):
    id: str
    name: str
    email: str
    region: str
    joined_on: date
    active: bool
    capacity: int


class ClientIn(StrictModel):
    id: str
    name: str
    industry: str
    size: str
    region: str
    created_on: date


class DealIn(StrictModel):
    id: str
    title: str
    value: int
    status: str
    stage: str
    created_at: date
    qualified_at: Optional[date] = None
    proposal_at: Optional[date] = None
    negotiation_at: Optional[date] = None
    expected_close_date: date
    closed_at: Optional[date] = None
    domain: str
    client_id: str
    owner_id: Optional[str] = None


class ActivityIn(StrictModel):
    id: str
    type: str
    date: date
    outcome: str
    deal_id: str
    sales_person_id: str


def make_update_model(model: type[BaseModel]) -> type[BaseModel]:
    """PATCH body: every field optional, id not changeable."""
    fields = {
        name: (Optional[f.annotation], None)
        for name, f in model.model_fields.items()
        if name != "id"
    }
    return create_model(model.__name__.replace("In", "Update"), __base__=StrictModel, **fields)


# ---- generic CRUD ----

def build_router(table: str, create_model_: type[BaseModel]) -> APIRouter:
    update_model = make_update_model(create_model_)
    columns = list(create_model_.model_fields) + ["inserted_at"]
    tbl = sql.Identifier(table)
    router = APIRouter(prefix=f"/{table}", tags=[table], dependencies=[Depends(require_api_key)])

    async def run(request: Request, query: sql.Composable, params: tuple = ()):
        try:
            async with request.app.state.pool.connection() as conn:
                cur = await conn.execute(query, params)
                return await cur.fetchall() if cur.description else []
        except errors.UniqueViolation:
            raise HTTPException(409, f"{table}: id already exists")
        except errors.ForeignKeyViolation as e:
            raise HTTPException(409, f"Foreign key violation: {e.diag.message_detail}")
        except (errors.NotNullViolation, errors.CheckViolation, errors.DataError) as e:
            raise HTTPException(422, e.diag.message_primary)

    @router.get("")
    async def list_rows(
        request: Request,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        order_by: str = Query("id"),
        desc: bool = False,
    ):
        """List rows. Any column can also be used as an equality filter, e.g. ?stage=won&client_id=c1."""
        if order_by not in columns:
            raise HTTPException(422, f"order_by must be one of {columns}")
        reserved = {"limit", "offset", "order_by", "desc"}
        filters = {k: v for k, v in request.query_params.items() if k not in reserved}
        unknown = set(filters) - set(columns)
        if unknown:
            raise HTTPException(422, f"Unknown filter column(s): {sorted(unknown)}")

        query = sql.SQL("SELECT * FROM {}").format(tbl)
        if filters:
            conds = [sql.SQL("{}::text = %s").format(sql.Identifier(c)) for c in filters]
            query += sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conds)
        query += sql.SQL(" ORDER BY {} {} LIMIT %s OFFSET %s").format(
            sql.Identifier(order_by), sql.SQL("DESC" if desc else "ASC")
        )
        return await run(request, query, (*filters.values(), limit, offset))

    @router.get("/{row_id}")
    async def get_row(request: Request, row_id: str):
        rows = await run(request, sql.SQL("SELECT * FROM {} WHERE id = %s").format(tbl), (row_id,))
        if not rows:
            raise HTTPException(404, f"{table} '{row_id}' not found")
        return rows[0]

    @router.post("", status_code=201)
    async def create_row(request: Request, body: create_model_):  # type: ignore[valid-type]
        data = body.model_dump()
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
            tbl,
            sql.SQL(", ").join(map(sql.Identifier, data)),
            sql.SQL(", ").join(sql.Placeholder() * len(data)),
        )
        return (await run(request, query, tuple(data.values())))[0]

    @router.patch("/{row_id}")
    async def update_row(request: Request, row_id: str, body: update_model):  # type: ignore[valid-type]
        data = body.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(422, "No fields to update")
        query = sql.SQL("UPDATE {} SET {} WHERE id = %s RETURNING *").format(
            tbl,
            sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(c)) for c in data),
        )
        rows = await run(request, query, (*data.values(), row_id))
        if not rows:
            raise HTTPException(404, f"{table} '{row_id}' not found")
        return rows[0]

    @router.delete("/{row_id}")
    async def delete_row(request: Request, row_id: str):
        rows = await run(
            request, sql.SQL("DELETE FROM {} WHERE id = %s RETURNING id").format(tbl), (row_id,)
        )
        if not rows:
            raise HTTPException(404, f"{table} '{row_id}' not found")
        return {"deleted": row_id}

    return router


for table_name, model in [
    ("sales_people", SalesPersonIn),
    ("clients", ClientIn),
    ("deals", DealIn),
    ("activities", ActivityIn),
]:
    app.include_router(build_router(table_name, model))


@app.get("/health", tags=["meta"])
async def health(request: Request):
    async with request.app.state.pool.connection() as conn:
        await conn.execute("SELECT 1")
    return {"status": "ok"}
