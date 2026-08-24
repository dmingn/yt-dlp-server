import { useState, type MouseEvent } from "react";

import { cancelJob } from "./api.ts";
import { formatTime } from "./datetime.ts";
import JobLog from "./JobLog.tsx";
import type { JobDetail, JobSummary } from "./types.ts";

type Props = {
  job: JobSummary;
  selected: boolean;
  detail: JobDetail | null;
  onSelect: (id: string) => void;
  onChanged: () => Promise<void>;
};

export default function JobCard({
  job,
  selected,
  detail,
  onSelect,
  onChanged,
}: Props) {
  const logText =
    selected && detail
      ? (detail.log?.lines || []).join("") || "(no log output yet)"
      : null;
  const [cancelLabel, setCancelLabel] = useState<"Cancel" | "Cancel failed">(
    "Cancel",
  );
  const [cancelDisabled, setCancelDisabled] = useState<boolean>(false);

  async function onCancel(event: MouseEvent) {
    event.stopPropagation();
    setCancelDisabled(true);
    try {
      await cancelJob(job.id);
      await onChanged();
    } catch {
      setCancelDisabled(false);
      setCancelLabel("Cancel failed");
      setTimeout(() => setCancelLabel("Cancel"), 1500);
    }
  }

  const canCancel = job.status === "queued" || job.status === "running";

  return (
    <article
      data-job-id={job.id}
      className={selected ? "selected" : undefined}
      onClick={() => onSelect(job.id)}
    >
      <div className="row">
        <div className="url">{job.url}</div>
        <div className="status">{job.status}</div>
      </div>
      <div className="meta">
        created {formatTime(job.created_at)}
        {job.scheduled_at ? ` · scheduled ${formatTime(job.scheduled_at)}` : ""}
        {` · logs ${job.log_line_count}`}
        {job.error ? ` · ${job.error}` : ""}
      </div>
      {canCancel ? (
        <div className="actions">
          <button
            type="button"
            className="secondary danger"
            disabled={cancelDisabled}
            onClick={onCancel}
          >
            {cancelLabel}
          </button>
        </div>
      ) : null}
      {logText !== null ? <JobLog text={logText} /> : null}
    </article>
  );
}
