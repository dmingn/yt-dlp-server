import type { JobDetail, JobSummary } from "./types.ts";

async function errorDetail(res: Response): Promise<string> {
  const body: unknown = await res.json().catch(() => null);
  if (
    body &&
    typeof body === "object" &&
    "detail" in body &&
    typeof body.detail === "string"
  ) {
    return body.detail;
  }
  return `Request failed (${res.status})`;
}

async function postJson(path: string, body: unknown): Promise<Response> {
  return fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function listJobs(): Promise<JobSummary[]> {
  const res = await postJson("/api/listJobs", {});
  if (!res.ok) throw new Error("Failed to load jobs");
  return res.json() as Promise<JobSummary[]>;
}

export async function getJob(id: string): Promise<JobDetail | null> {
  const res = await postJson("/api/getJob", { id });
  if (!res.ok) return null;
  return res.json() as Promise<JobDetail>;
}

export async function createJob(body: {
  url: string;
  scheduled_at?: string;
}): Promise<JobSummary> {
  const res = await postJson("/api/createJob", body);
  if (!res.ok) {
    throw new Error(await errorDetail(res));
  }
  return res.json() as Promise<JobSummary>;
}

export async function cancelJob(id: string): Promise<void> {
  const res = await postJson("/api/cancelJob", { id });
  if (!res.ok) throw new Error("Cancel failed");
}

export async function rescheduleJob(
  id: string,
  scheduled_at: string,
): Promise<void> {
  const res = await postJson("/api/rescheduleJob", { id, scheduled_at });
  if (!res.ok) throw new Error("Reschedule failed");
}
