"""Jobs you paste, scored by the Freelance Manager (P5-05), and their proposals (P5-06).

    GET  /api/jobs?status=new|proposal|sent|skipped|all
    POST /api/jobs/{id}/skip
"""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from junior.audit import audit
from junior.db import Job, session_scope
from junior.db.models import utcnow
from junior.freelance.scam import scam_signs

router = APIRouter()
STATUSES = ("new", "proposal", "sent", "skipped")
Verdict = Literal["apply", "maybe", "skip"]


class ClientInfo(BaseModel):
    payment_verified: bool | None = None
    rating: float | None = None
    reviews: int | None = None
    total_spent: str = ""
    hires: int | None = None
    hire_rate: str = ""
    location: str = ""


class JobScore(BaseModel):
    """What the Freelance Manager reads from a job post and how it judges it."""

    title: str = Field(description="The job's title, as posted.")
    budget: str = Field(default="", description="Fixed price or hourly range, as posted; empty if not shown.")
    skills: list[str] = Field(default_factory=list, description="The skills the job asks for.")
    client: ClientInfo = Field(default_factory=ClientInfo, description="Client details shown in the post; leave unknown ones empty.")
    score: int = Field(description="0 to 10: how good a fit and an opportunity this is for the user.")
    verdict: Verdict = Field(description="apply, maybe or skip.")
    reasons: list[str] = Field(default_factory=list, description="2 to 5 short reasons for the score.")
    concerns: list[str] = Field(default_factory=list, description="Warning signs, if any.")


class JobOut(BaseModel):
    id: int
    platform: str
    title: str
    url: str
    budget: str
    skills: list[str]
    client: dict
    score: int
    verdict: str
    reasons: list[str]
    concerns: list[str]
    scam_signs: list[str]
    status: str
    approval_id: int | None
    created_at: datetime


def _out(j: Job) -> JobOut:
    return JobOut(
        id=j.id, platform=j.platform, title=j.title, url=j.url, budget=j.budget, skills=j.skills, client=j.client,
        score=j.score, verdict=j.verdict, reasons=j.reasons, concerns=j.concerns, scam_signs=j.scam_signs,
        status=j.status, approval_id=j.approval_id, created_at=j.created_at,
    )


def save_job(score: JobScore, text: str, url: str = "", platform: str = "upwork", paste_id: int | None = None) -> JobOut:
    """Save a scored job. Scam signs found by code always make it a skip."""
    signs = scam_signs(text)
    verdict, value = score.verdict, max(0, min(10, score.score))
    if signs:
        verdict, value = "skip", min(value, 2)
    with session_scope() as s:
        job = Job(
            platform=platform,
            title=score.title.strip()[:200] or "A job",
            url=url[:500] if url.startswith(("https://", "http://")) else "",
            text=text,
            budget=score.budget[:100],
            skills=[k.strip() for k in score.skills if k.strip()][:20],
            client=score.client.model_dump(),
            score=value,
            verdict=verdict,
            reasons=score.reasons[:5],
            concerns=score.concerns[:5],
            scam_signs=signs,
            status="skipped" if verdict == "skip" and signs else "new",
            paste_id=paste_id,
        )
        s.add(job)
        s.flush()
        out = _out(job)
    audit("action", "job_scored", detail={"id": out.id, "score": out.score, "verdict": out.verdict, "scam_signs": signs})
    return out


def get_job(job_id: int) -> JobOut | None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        return _out(job) if job else None


def link_proposal(job_id: int, approval_id: int) -> None:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if job:
            job.approval_id = approval_id
            if job.status in ("new", "skipped"):
                job.status = "proposal"
            job.updated_at = utcnow()


def proposal_sent(job_id: int) -> None:
    """The proposal card was marked as sent: so is the job."""
    with session_scope() as s:
        job = s.get(Job, job_id)
        if job:
            job.status = "sent"
            job.updated_at = utcnow()


def recent_jobs(limit: int = 10) -> list[JobOut]:
    with session_scope() as s:
        return [_out(j) for j in s.scalars(select(Job).order_by(Job.id.desc()).limit(limit))]


@router.get("/api/jobs", response_model=list[JobOut])
def list_jobs(status: str = "all", limit: int = 100) -> list[JobOut]:
    if status != "all" and status not in STATUSES:
        raise HTTPException(422, f"status must be 'all' or one of {list(STATUSES)}")
    with session_scope() as s:
        q = select(Job).order_by(Job.id.desc()).limit(min(limit, 500))
        if status != "all":
            q = q.where(Job.status == status)
        return [_out(j) for j in s.scalars(q)]


@router.post("/api/jobs/{job_id}/skip", response_model=JobOut)
def skip_job(job_id: int) -> JobOut:
    with session_scope() as s:
        job = s.get(Job, job_id)
        if job is None:
            raise HTTPException(404, f"Job {job_id} doesn't exist.")
        job.status = "skipped"
        job.updated_at = utcnow()
        s.flush()
        return _out(job)
