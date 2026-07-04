from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import DbSession
from app.db.models import (
    AgentRun,
    Document,
    SemanticCapsule,
    SemanticRelation,
    Span,
    Thesis,
)

router = APIRouter(tags=["stats"])


class CountsOut(BaseModel):
    documents: int
    spans: int
    capsules: int
    relations: int
    theses: int


class ModelUsageRow(BaseModel):
    run_type: str
    model: str
    calls: int
    prompt_tokens: int
    completion_tokens: int
    cost_estimate_usd: float


class StatsOverviewOut(BaseModel):
    counts: CountsOut
    lifecycle: dict[str, int]
    model_usage: list[ModelUsageRow]


@router.get("/stats/overview", response_model=StatsOverviewOut)
async def stats_overview(db: DbSession) -> StatsOverviewOut:
    documents = (await db.execute(select(func.count()).select_from(Document))).scalar_one()
    spans = (await db.execute(select(func.count()).select_from(Span))).scalar_one()
    capsules = (await db.execute(select(func.count()).select_from(SemanticCapsule))).scalar_one()
    relations = (await db.execute(select(func.count()).select_from(SemanticRelation))).scalar_one()
    theses = (await db.execute(select(func.count()).select_from(Thesis))).scalar_one()

    lifecycle_rows = (
        await db.execute(
            select(SemanticCapsule.lifecycle_state, func.count()).group_by(
                SemanticCapsule.lifecycle_state
            )
        )
    ).all()
    lifecycle = {state: count for state, count in lifecycle_rows}

    usage_rows = (
        await db.execute(
            select(
                AgentRun.run_type,
                AgentRun.model,
                func.count().label("calls"),
                func.coalesce(func.sum(AgentRun.prompt_tokens), 0).label("prompt_tokens"),
                func.coalesce(func.sum(AgentRun.completion_tokens), 0).label("completion_tokens"),
                func.coalesce(func.sum(AgentRun.cost_estimate), 0.0).label("cost_estimate_usd"),
            )
            .group_by(AgentRun.run_type, AgentRun.model)
            .order_by(AgentRun.run_type, AgentRun.model)
        )
    ).all()

    model_usage = [
        ModelUsageRow(
            run_type=row.run_type,
            model=row.model or "",
            calls=row.calls,
            prompt_tokens=int(row.prompt_tokens),
            completion_tokens=int(row.completion_tokens),
            cost_estimate_usd=float(row.cost_estimate_usd),
        )
        for row in usage_rows
    ]

    return StatsOverviewOut(
        counts=CountsOut(
            documents=documents,
            spans=spans,
            capsules=capsules,
            relations=relations,
            theses=theses,
        ),
        lifecycle=lifecycle,
        model_usage=model_usage,
    )
