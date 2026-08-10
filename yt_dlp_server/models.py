from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, NewType, assert_never, get_args

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, TypeAdapter

JobId = NewType("JobId", str)


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class JobLog(BaseModel):
    model_config = ConfigDict(frozen=True)

    lines: tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.lines)


class _JobBase(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: JobId
    url: AnyHttpUrl
    created_at: datetime


class QueuedJob(_JobBase):
    status: Literal[JobStatus.queued] = JobStatus.queued

    def start(self, *, started_at: datetime) -> RunningJob:
        return RunningJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            started_at=started_at,
            log=JobLog(),
        )

    def cancel(self, *, finished_at: datetime) -> CancelledJob:
        return CancelledJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            finished_at=finished_at,
            log=JobLog(),
        )


class RunningJob(_JobBase):
    status: Literal[JobStatus.running] = JobStatus.running
    started_at: datetime
    log: JobLog

    def requeue(self) -> QueuedJob:
        return QueuedJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
        )

    def succeed(self, *, finished_at: datetime, exit_code: int = 0) -> SucceededJob:
        return SucceededJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            log=self.log,
        )

    def fail(
        self,
        *,
        finished_at: datetime,
        error: str,
        exit_code: int | None = None,
    ) -> FailedJob:
        return FailedJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            log=self.log,
            error=error,
        )

    def cancel(self, *, finished_at: datetime) -> CancelledJob:
        return CancelledJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=finished_at,
            log=self.log,
        )


class SucceededJob(_JobBase):
    status: Literal[JobStatus.succeeded] = JobStatus.succeeded
    started_at: datetime
    finished_at: datetime
    exit_code: int
    log: JobLog


class FailedJob(_JobBase):
    status: Literal[JobStatus.failed] = JobStatus.failed
    started_at: datetime
    finished_at: datetime
    exit_code: int | None = None
    log: JobLog
    error: str


class CancelledJob(_JobBase):
    status: Literal[JobStatus.cancelled] = JobStatus.cancelled
    started_at: datetime | None = None
    finished_at: datetime
    log: JobLog


Job = Annotated[
    QueuedJob | RunningJob | SucceededJob | FailedJob | CancelledJob,
    Field(discriminator="status"),
]

JOB_ADAPTER: TypeAdapter[Job] = TypeAdapter(Job)

UnfinishedJob = QueuedJob | RunningJob
FinishedJob = SucceededJob | FailedJob | CancelledJob

UNFINISHED_STATUSES = tuple(
    t.model_fields["status"].default.value for t in get_args(UnfinishedJob)
)
FINISHED_STATUSES = tuple(
    t.model_fields["status"].default.value for t in get_args(FinishedJob)
)


class JobSummary(BaseModel):
    id: JobId
    url: AnyHttpUrl
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    exit_code: int | None = None
    log_line_count: int
    error: str | None = None

    @classmethod
    def from_job(cls, job: Job) -> JobSummary:
        if isinstance(job, QueuedJob):
            return cls(
                id=job.id,
                url=job.url,
                status=job.status,
                created_at=job.created_at,
                log_line_count=0,
            )
        if isinstance(job, RunningJob):
            return cls(
                id=job.id,
                url=job.url,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                log_line_count=len(job.log),
            )
        if isinstance(job, SucceededJob):
            return cls(
                id=job.id,
                url=job.url,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                exit_code=job.exit_code,
                log_line_count=len(job.log),
            )
        if isinstance(job, FailedJob):
            return cls(
                id=job.id,
                url=job.url,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                exit_code=job.exit_code,
                log_line_count=len(job.log),
                error=job.error,
            )
        if isinstance(job, CancelledJob):
            return cls(
                id=job.id,
                url=job.url,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                log_line_count=len(job.log),
            )
        assert_never(job)
