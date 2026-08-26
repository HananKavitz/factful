export interface User {
  id: number;
  email: string;
  name: string;
  picture: string | null;
}

export type JobStatusName = "queued" | "running" | "done" | "error" | "cancelled";

export interface JobStatus {
  job_id: string;
  status: JobStatusName;
  stage: string | null;
  error: string | null;
  story_id: number | null;
  progress: number | null;
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

export interface DeviceExample {
  label: string;
  count: number;
  excerpt: string;
}

export interface StyleMetrics {
  avg_sentence_words: number;
  avg_paragraph_sentences: number;
  paragraph_length_dist: number[];
  numeric_density: number;
}

export interface StyleExtraction {
  voice: string;
  tone: string;
  hook_patterns: string[];
  story_beats: string[];
  transitions: string[];
  rhetorical_devices: DeviceExample[];
  direct_address: DeviceExample[];
  characterization: DeviceExample[];
  opinion_hedges: string[];
  comparatives: string[];
  modals: string[];
  numeric_style: string;
  cta_style: string | null;
  signoff_style: string | null;
}

export interface StyleProfile {
  name: string;
  metrics: StyleMetrics;
  extraction: StyleExtraction;
  source_confidence: number;
}

export interface Settings {
  style: StyleProfile | null;
  temperature: number | null;
  top_p: number | null;
}
