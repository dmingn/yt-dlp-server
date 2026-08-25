import { useMemo, useState, type SubmitEvent } from "react";

import { createJob, rescheduleJob } from "./api.ts";
import { toDatetimeLocalValue } from "./datetime.ts";
import ScheduleCard from "./ScheduleCard.tsx";
import type { JobSummary } from "./types.ts";

function timezoneHint(): string {
  const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const offsetPart = new Intl.DateTimeFormat("en-US", {
    timeZoneName: "longOffset",
  })
    .formatToParts(new Date())
    .find((part) => part.type === "timeZoneName");
  const offset = offsetPart ? offsetPart.value : "";
  return `Times are this browser’s local timezone (${timeZone}, ${offset}).`;
}

type Props = {
  hidden: boolean;
  jobs: JobSummary[];
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
};

export default function SchedulesView({
  hidden,
  jobs,
  onChanged,
  onError,
}: Props) {
  const [url, setUrl] = useState<string>("");
  const [at, setAt] = useState<string>("");
  const [isCreatingSchedule, setIsCreatingSchedule] = useState<boolean>(false);
  const [draftAt, setDraftAt] = useState<Record<string, string>>({});
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const tzHint = useMemo(() => timezoneHint(), []);

  async function onSubmit(event: SubmitEvent) {
    event.preventDefault();
    onError("");
    setIsCreatingSchedule(true);
    try {
      await createJob({
        url: url.trim(),
        scheduled_at: new Date(at).toISOString(),
      });
      setUrl("");
      setAt("");
      await onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsCreatingSchedule(false);
    }
  }

  return (
    <div id="schedules-view" hidden={hidden}>
      <form id="schedule-form" className="wrap" onSubmit={onSubmit}>
        <input
          id="schedule-url-input"
          type="url"
          name="url"
          placeholder="https://..."
          required
          autoComplete="off"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
        />
        <input
          id="schedule-at-input"
          type="datetime-local"
          required
          aria-describedby="schedule-tz-hint"
          value={at}
          onChange={(event) => setAt(event.target.value)}
        />
        <button type="submit" id="schedule-btn" disabled={isCreatingSchedule}>
          Schedule
        </button>
      </form>
      <p id="schedule-tz-hint" className="hint">
        {tzHint}
      </p>
      <section id="schedules" className="jobs" aria-live="polite">
        {jobs.length === 0 ? (
          <p className="empty">No schedules yet.</p>
        ) : (
          jobs.map((job) => (
            <ScheduleCard
              key={job.id}
              job={job}
              atValue={
                focusedId === job.id && draftAt[job.id] !== undefined
                  ? draftAt[job.id]
                  : toDatetimeLocalValue(job.scheduled_at ?? "")
              }
              onFocusAt={() => {
                setFocusedId(job.id);
                setDraftAt((prev) =>
                  prev[job.id] !== undefined
                    ? prev
                    : {
                        ...prev,
                        [job.id]: toDatetimeLocalValue(job.scheduled_at ?? ""),
                      },
                );
              }}
              onChangeAt={(value) =>
                setDraftAt((prev) => ({ ...prev, [job.id]: value }))
              }
              onBlurAt={() => setFocusedId(null)}
              onSave={async () => {
                const value =
                  draftAt[job.id] ??
                  toDatetimeLocalValue(job.scheduled_at ?? "");
                onError("");
                await rescheduleJob(job.id, new Date(value).toISOString());
                setDraftAt((prev) => {
                  const next = { ...prev };
                  delete next[job.id];
                  return next;
                });
                await onChanged();
              }}
              onChanged={onChanged}
              onError={onError}
            />
          ))
        )}
      </section>
    </div>
  );
}
