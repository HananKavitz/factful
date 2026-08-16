export interface User {
  id: number;
  email: string;
  name: string;
  picture: string | null;
}

export type JobStatusName = "queued" | "running" | "done" | "error";

export interface JobStatus {
  job_id: string;
  status: JobStatusName;
  stage: string | null;
  error: string | null;
  story_id: number | null;
}

export interface StorySummary {
  id: number;
  title: string;
  topic: string;
  score: number | null;
  created_at: string;
  updated_at: string;
}

export interface StoryDetail extends StorySummary {
  angle: string | null;
  instructions: string | null;
  markdown: string;
}
