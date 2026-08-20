import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCancelJobMutation, useGetJobQuery } from "../jobs/jobsApi";
import { useCreateStoryMutation } from "../stories/storiesApi";

interface CreateStoryModalProps {
  onClose: () => void;
  initialValues?: {
    topic: string;
    angle: string | null;
    instructions: string | null;
  };
}

function formatElapsed(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

export function CreateStoryModal({ onClose, initialValues }: CreateStoryModalProps) {
  const [topic, setTopic] = useState(initialValues?.topic ?? "");
  const [angle, setAngle] = useState(initialValues?.angle ?? "");
  const [instructions, setInstructions] = useState(initialValues?.instructions ?? "");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [createStory, { isLoading }] = useCreateStoryMutation();
  const [cancelJob, { isLoading: stopping }] = useCancelJobMutation();
  const { data: job } = useGetJobQuery(jobId ?? "", {
    skip: jobId === null,
    pollingInterval: 1500,
  });
  const navigate = useNavigate();
  const topicRef = useRef<HTMLTextAreaElement>(null);
  const mouseDownTarget = useRef<EventTarget | null>(null);

  const isRegenerate = initialValues !== undefined;

  const running =
    jobId !== null &&
    job?.status !== "done" &&
    job?.status !== "error" &&
    job?.status !== "cancelled";

  useEffect(() => {
    topicRef.current?.focus();
  }, []);

  useEffect(() => {
    if (running) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [running, onClose]);

  useEffect(() => {
    if (job?.status === "done" && job.story_id != null) {
      navigate(`/stories/${job.story_id}`, { replace: true });
    }
  }, [job, navigate]);

  useEffect(() => {
    if (job?.status === "cancelled") {
      onClose();
    }
  }, [job, onClose]);

  useEffect(() => {
    if (job?.status === "error") {
      setError(job.error ?? "Generation failed");
    }
  }, [job]);

  useEffect(() => {
    if (!running) {
      setElapsed(0);
      return;
    }
    const timer = window.setInterval(() => setElapsed((current) => current + 1), 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      const result = await createStory({
        topic: topic.trim(),
        angle: angle.trim() || null,
        instructions: instructions.trim() || null,
      }).unwrap();
      setJobId(result.job_id);
    } catch {
      setError("Could not start generation. Please try again.");
    }
  };

  const handleStop = async () => {
    if (jobId === null) return;
    try {
      await cancelJob(jobId).unwrap();
      onClose();
    } catch {
      setError("Could not cancel the run. Please try again.");
    }
  };

  return (
    <div
      className="fixed inset-0 z-10 flex items-center justify-center bg-slate-900/40 px-4"
      onMouseDown={(event) => {
        mouseDownTarget.current = event.target;
      }}
      onClick={(event) => {
        if (running) return;
        if (mouseDownTarget.current === event.currentTarget) onClose();
        mouseDownTarget.current = null;
      }}
    >
      <div
        className="w-full max-w-4xl rounded-lg bg-white p-8 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="text-xl font-semibold text-slate-900">
          {running
            ? "Generating story"
            : isRegenerate
              ? "Regenerate story"
              : "Create a new story"}
        </h2>

        {running ? (
          <div className="mt-6 space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-base text-slate-500">
                {job?.stage ?? "queued"}
                {"…"}
              </p>
              <span className="text-sm text-slate-400">
                <span className="mr-1">elapsed</span>
                <span className="tabular-nums">{formatElapsed(elapsed)}</span>
              </span>
            </div>
            <div className="h-2 w-full animate-pulse rounded-full bg-slate-200" />
            {error && <p className="text-base text-red-600">{error}</p>}
            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={handleStop}
                disabled={stopping}
                className="rounded-md border border-slate-300 px-5 py-2.5 text-base text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              >
                {stopping ? "Stopping…" : "Stop"}
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <label className="block">
              <span className="text-base font-medium text-slate-700">Topic</span>
              <textarea
                ref={topicRef}
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder="e.g. Chip demand in 2026"
                rows={3}
                className="mt-1 w-full rounded-md border border-slate-300 px-4 py-3 text-base"
                required
              />
            </label>
            <label className="block">
              <span className="text-base font-medium text-slate-700">
                Angle <span className="font-normal text-slate-400">(optional)</span>
              </span>
              <input
                value={angle}
                onChange={(event) => setAngle(event.target.value)}
                placeholder="e.g. key numbers and statistics"
                className="mt-1 w-full rounded-md border border-slate-300 px-4 py-3 text-base"
              />
            </label>
            <label className="block">
              <span className="text-base font-medium text-slate-700">
                Instructions <span className="font-normal text-slate-400">(optional)</span>
              </span>
              <textarea
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
                rows={5}
                className="mt-1 w-full rounded-md border border-slate-300 px-4 py-3 text-base"
              />
            </label>
            {error && <p className="text-base text-red-600">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-slate-300 px-5 py-2.5 text-base text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading || !topic.trim()}
                className="rounded-md bg-blush px-5 py-2.5 text-base font-medium text-slate-900 hover:bg-blush-dark disabled:opacity-50"
              >
                Generate
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
