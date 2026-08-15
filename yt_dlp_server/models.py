from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, NewType, assert_never, get_args

from pydantic import (
    AnyHttpUrl,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Discriminator,
    Tag,
    TypeAdapter,
)

JobId = NewType("JobId", str)


class JobStatus(str, Enum):
    queued = "queued"
    scheduled = "scheduled"
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

    def start(self, *, started_at: datetime) -> ImmediateRunningJob:
        return ImmediateRunningJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            started_at=started_at,
            log=JobLog(),
        )

    def cancel(self, *, finished_at: datetime) -> ImmediateCancelledJob:
        return ImmediateCancelledJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            finished_at=finished_at,
            log=JobLog(),
        )


class ScheduledJob(_JobBase):
    status: Literal[JobStatus.scheduled] = JobStatus.scheduled
    scheduled_at: AwareDatetime

    def start(self, *, started_at: datetime) -> ScheduledRunningJob:
        return ScheduledRunningJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            started_at=started_at,
            scheduled_at=self.scheduled_at,
            log=JobLog(),
        )

    def cancel(self, *, finished_at: datetime) -> ScheduledCancelledJob:
        return ScheduledCancelledJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            finished_at=finished_at,
            scheduled_at=self.scheduled_at,
            log=JobLog(),
        )


class _RunningJobBase(_JobBase):
    status: Literal[JobStatus.running] = JobStatus.running
    started_at: datetime
    log: JobLog


class ImmediateRunningJob(_RunningJobBase):
    def to_waiting(self) -> QueuedJob:
        return QueuedJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
        )

    def succeed(
        self, *, finished_at: datetime, exit_code: int = 0
    ) -> ImmediateSucceededJob:
        return ImmediateSucceededJob(
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
    ) -> ImmediateFailedJob:
        return ImmediateFailedJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            log=self.log,
            error=error,
        )

    def cancel(self, *, finished_at: datetime) -> ImmediateCancelledJob:
        return ImmediateCancelledJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=finished_at,
            log=self.log,
        )


class ScheduledRunningJob(_RunningJobBase):
    scheduled_at: AwareDatetime

    def to_waiting(self) -> ScheduledJob:
        return ScheduledJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            scheduled_at=self.scheduled_at,
        )

    def succeed(
        self, *, finished_at: datetime, exit_code: int = 0
    ) -> ScheduledSucceededJob:
        return ScheduledSucceededJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            scheduled_at=self.scheduled_at,
            log=self.log,
        )

    def fail(
        self,
        *,
        finished_at: datetime,
        error: str,
        exit_code: int | None = None,
    ) -> ScheduledFailedJob:
        return ScheduledFailedJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=finished_at,
            exit_code=exit_code,
            scheduled_at=self.scheduled_at,
            log=self.log,
            error=error,
        )

    def cancel(self, *, finished_at: datetime) -> ScheduledCancelledJob:
        return ScheduledCancelledJob(
            id=self.id,
            url=self.url,
            created_at=self.created_at,
            started_at=self.started_at,
            finished_at=finished_at,
            scheduled_at=self.scheduled_at,
            log=self.log,
        )


class _SucceededJobBase(_JobBase):
    status: Literal[JobStatus.succeeded] = JobStatus.succeeded
    started_at: datetime
    finished_at: datetime
    exit_code: int
    log: JobLog


class ImmediateSucceededJob(_SucceededJobBase):
    pass


class ScheduledSucceededJob(_SucceededJobBase):
    scheduled_at: AwareDatetime


class _FailedJobBase(_JobBase):
    status: Literal[JobStatus.failed] = JobStatus.failed
    started_at: datetime
    finished_at: datetime
    exit_code: int | None = None
    log: JobLog
    error: str


class ImmediateFailedJob(_FailedJobBase):
    pass


class ScheduledFailedJob(_FailedJobBase):
    scheduled_at: AwareDatetime


class _CancelledJobBase(_JobBase):
    status: Literal[JobStatus.cancelled] = JobStatus.cancelled
    started_at: datetime | None = None
    finished_at: datetime
    log: JobLog


class ImmediateCancelledJob(_CancelledJobBase):
    pass


class ScheduledCancelledJob(_CancelledJobBase):
    scheduled_at: AwareDatetime


RunningJob = ImmediateRunningJob | ScheduledRunningJob
SucceededJob = ImmediateSucceededJob | ScheduledSucceededJob
FailedJob = ImmediateFailedJob | ScheduledFailedJob
CancelledJob = ImmediateCancelledJob | ScheduledCancelledJob


def _job_discriminator(value: Any) -> str:
    if isinstance(value, dict):
        status = value.get("status")
        scheduled_at = value.get("scheduled_at")
    else:
        status = value.status
        scheduled_at = getattr(value, "scheduled_at", None)
    if isinstance(status, JobStatus):
        status = status.value
    if (
        status
        in {
            JobStatus.running.value,
            JobStatus.succeeded.value,
            JobStatus.failed.value,
            JobStatus.cancelled.value,
        }
        and scheduled_at is not None
    ):
        return f"scheduled-{status}"
    return str(status)


Job = Annotated[
    Annotated[QueuedJob, Tag("queued")]
    | Annotated[ScheduledJob, Tag("scheduled")]
    | Annotated[ImmediateRunningJob, Tag("running")]
    | Annotated[ScheduledRunningJob, Tag("scheduled-running")]
    | Annotated[ImmediateSucceededJob, Tag("succeeded")]
    | Annotated[ScheduledSucceededJob, Tag("scheduled-succeeded")]
    | Annotated[ImmediateFailedJob, Tag("failed")]
    | Annotated[ScheduledFailedJob, Tag("scheduled-failed")]
    | Annotated[ImmediateCancelledJob, Tag("cancelled")]
    | Annotated[ScheduledCancelledJob, Tag("scheduled-cancelled")],
    Discriminator(_job_discriminator),
]

JOB_ADAPTER: TypeAdapter[Job] = TypeAdapter(Job)

UnfinishedJob = QueuedJob | ScheduledJob | RunningJob
FinishedJob = SucceededJob | FailedJob | CancelledJob

UNFINISHED_STATUSES = tuple(
    dict.fromkeys(
        t.model_fields["status"].default.value for t in get_args(UnfinishedJob)
    )
)
FINISHED_STATUSES = tuple(
    dict.fromkeys(t.model_fields["status"].default.value for t in get_args(FinishedJob))
)


class JobSummary(BaseModel):
    id: JobId
    url: AnyHttpUrl
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    scheduled_at: AwareDatetime | None = None
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
        if isinstance(job, ScheduledJob):
            return cls(
                id=job.id,
                url=job.url,
                status=job.status,
                created_at=job.created_at,
                scheduled_at=job.scheduled_at,
                log_line_count=0,
            )
        if isinstance(job, ImmediateRunningJob):
            return cls(
                id=job.id,
                url=job.url,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                log_line_count=len(job.log),
            )
        if isinstance(job, ScheduledRunningJob):
            return cls(
                id=job.id,
                url=job.url,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                scheduled_at=job.scheduled_at,
                log_line_count=len(job.log),
            )
        if isinstance(job, ImmediateSucceededJob):
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
        if isinstance(job, ScheduledSucceededJob):
            return cls(
                id=job.id,
                url=job.url,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                scheduled_at=job.scheduled_at,
                exit_code=job.exit_code,
                log_line_count=len(job.log),
            )
        if isinstance(job, ImmediateFailedJob):
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
        if isinstance(job, ScheduledFailedJob):
            return cls(
                id=job.id,
                url=job.url,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                scheduled_at=job.scheduled_at,
                exit_code=job.exit_code,
                log_line_count=len(job.log),
                error=job.error,
            )
        if isinstance(job, ImmediateCancelledJob):
            return cls(
                id=job.id,
                url=job.url,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                log_line_count=len(job.log),
            )
        if isinstance(job, ScheduledCancelledJob):
            return cls(
                id=job.id,
                url=job.url,
                status=job.status,
                created_at=job.created_at,
                started_at=job.started_at,
                finished_at=job.finished_at,
                scheduled_at=job.scheduled_at,
                log_line_count=len(job.log),
            )
        assert_never(job)
