import { useState, type SubmitEvent } from "react";

import { createJob } from "./api.ts";
import JobCard from "./JobCard.tsx";
import type { JobDetail, JobSummary } from "./types.ts";

type Props = {
  hidden: boolean;
  jobs: JobSummary[];
  selectedId: string | null;
  selectedDetail: JobDetail | null;
  onSelect: (id: string) => void;
  onCreated: (id: string) => Promise<void>;
  onChanged: () => Promise<void>;
  onError: (message: string) => void;
};

export default function JobsView({
  hidden,
  jobs,
  selectedId,
  selectedDetail,
  onSelect,
  onCreated,
  onChanged,
  onError,
}: Props) {
  const [url, setUrl] = useState<string>("");
  const [isCreatingJob, setIsCreatingJob] = useState<boolean>(false);

  async function onSubmit(event: SubmitEvent) {
    event.preventDefault();
    onError("");
    setIsCreatingJob(true);
    try {
      const job = await createJob({ url: url.trim() });
      setUrl("");
      await onCreated(job.id);
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsCreatingJob(false);
    }
  }

  return (
    <div id="jobs-view" hidden={hidden}>
      <form id="submit-form" onSubmit={onSubmit}>
        <input
          id="url-input"
          type="url"
          name="url"
          placeholder="https://..."
          required
          autoComplete="off"
          value={url}
          onChange={(event) => setUrl(event.target.value)}
        />
        <button type="submit" id="submit-btn" disabled={isCreatingJob}>
          Download
        </button>
      </form>
      <section id="jobs" className="jobs" aria-live="polite">
        {jobs.length === 0 ? (
          <p className="empty">No jobs yet.</p>
        ) : (
          jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              selected={job.id === selectedId}
              detail={job.id === selectedId ? selectedDetail : null}
              onSelect={onSelect}
              onChanged={onChanged}
            />
          ))
        )}
      </section>
    </div>
  );
}
