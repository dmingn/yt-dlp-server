import { useCallback, useEffect, useRef, useState } from "react";

import { getJob, listJobs } from "./api.ts";
import JobsView from "./JobsView.tsx";
import SchedulesView from "./SchedulesView.tsx";
import type { JobDetail, JobSummary } from "./types.ts";

function currentView(): "jobs" | "schedules" {
  return location.hash === "#schedules" ? "schedules" : "jobs";
}

export default function App() {
  const version = window.__APP_VERSION__;
  const [view, setView] = useState<"jobs" | "schedules">(currentView);
  const [error, setError] = useState<string>("");
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<JobDetail | null>(null);
  const selectedIdRef = useRef<string | null>(selectedId);
  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  const refresh = useCallback(async (idOverride?: string | null) => {
    const listed = await listJobs();
    let nextId =
      idOverride !== undefined ? idOverride : selectedIdRef.current;
    let nextDetail: JobDetail | null = null;
    if (nextId) {
      nextDetail = await getJob(nextId);
      if (!nextDetail) nextId = null;
    }
    setSelectedId(nextId);
    selectedIdRef.current = nextId;
    setSelectedDetail(nextDetail);
    setJobs(listed);
  }, []);

  useEffect(() => {
    function onHashChange() {
      setView(currentView());
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  useEffect(() => {
    void refresh().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : String(err)),
    );
    const timer = setInterval(() => {
      void refresh().catch(() => {});
    }, 2000);
    return () => clearInterval(timer);
  }, [refresh]);

  const activeJobs = jobs.filter((job) => job.status !== "scheduled");
  const schedules = jobs
    .filter((job) => job.status === "scheduled")
    .sort((a, b) => (a.scheduled_at ?? "").localeCompare(b.scheduled_at ?? ""));

  return (
    <main>
      <h1>
        yt-dlp-server <span className="version">{version}</span>
      </h1>
      <p className="sub">
        Paste a video URL to download with the server’s fixed yt-dlp settings.
        Use Schedules to start at a chosen time.
      </p>
      <nav className="tabs">
        <a
          id="jobs-nav"
          href="#jobs"
          className={view === "jobs" ? "active" : undefined}
        >
          Jobs
        </a>
        <a
          id="schedules-nav"
          href="#schedules"
          className={view === "schedules" ? "active" : undefined}
        >
          Schedules
        </a>
      </nav>
      <p id="form-error" className="error" hidden={!error}>
        {error}
      </p>
      <JobsView
        hidden={view !== "jobs"}
        jobs={activeJobs}
        selectedId={selectedId}
        selectedDetail={selectedDetail}
        onSelect={(id) => {
          const next = selectedId === id ? null : id;
          void refresh(next);
        }}
        onCreated={(id) => refresh(id)}
        onChanged={() => refresh()}
        onError={setError}
      />
      <SchedulesView
        hidden={view !== "schedules"}
        jobs={schedules}
        onChanged={() => refresh()}
        onError={setError}
      />
    </main>
  );
}
