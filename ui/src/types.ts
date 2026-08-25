export type JobSummary = {
  id: string;
  url: string;
  status: string;
  created_at: string;
  scheduled_at: string | null;
  log_line_count: number;
  error: string | null;
};

export type JobDetail = JobSummary & {
  log?: { lines: string[] };
};
