import { useState } from "react";

import { cancelJob } from "./api.ts";
import { formatTime } from "./datetime.ts";
import type { JobSummary } from "./types.ts";

type Props = {
  job: JobSummary;
  atValue: string;
  onFocusAt: () => void;
  onChangeAt: (value: string) => void;
  onBlurAt: () => void;
  onSave: () => Promise<void>;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
};

export default function ScheduleCard({
  job,
  atValue,
  onFocusAt,
  onChangeAt,
  onBlurAt,
  onSave,
  onChanged,
  onError,
}: Props) {
  const [saveDisabled, setSaveDisabled] = useState<boolean>(false);
  const [cancelLabel, setCancelLabel] = useState<"Cancel" | "Cancel failed">(
    "Cancel",
  );
  const [cancelDisabled, setCancelDisabled] = useState<boolean>(false);

  async function onSaveClick() {
    onError("");
    setSaveDisabled(true);
    try {
      await onSave();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaveDisabled(false);
    }
  }

  async function onCancel() {
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

  return (
    <article data-job-id={job.id}>
      <div className="row">
        <div className="url">{job.url}</div>
        <div className="status">{job.status}</div>
      </div>
      <div className="meta">
        {job.scheduled_at ? `scheduled ${formatTime(job.scheduled_at)}` : null}
      </div>
      <div className="actions">
        <input
          type="datetime-local"
          aria-describedby="schedule-tz-hint"
          value={atValue}
          onFocus={onFocusAt}
          onChange={(event) => onChangeAt(event.target.value)}
          onBlur={onBlurAt}
        />
        <button
          type="button"
          className="secondary"
          disabled={saveDisabled}
          onClick={() => void onSaveClick()}
        >
          Save
        </button>
        <button
          type="button"
          className="secondary danger"
          disabled={cancelDisabled}
          onClick={onCancel}
        >
          {cancelLabel}
        </button>
      </div>
    </article>
  );
}
