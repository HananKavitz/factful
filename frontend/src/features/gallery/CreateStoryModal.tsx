import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useGetJobQuery } from "../jobs/jobsApi";
import { useCreateStoryMutation } from "../stories/storiesApi";

interface CreateStoryModalProps {
  onClose: () => void;
}

export function CreateStoryModal({ onClose }: CreateStoryModalProps) {
  const [topic, setTopic] = useState("");
  const [angle, setAngle] = useState("");
  const [instructions, setInstructions] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [createStory, { isLoading }] = useCreateStoryMutation();
  const { data: job } = useGetJobQuery(jobId ?? "", {
    skip: jobId === null,
    pollingInterval: 1500,
  });
  const navigate = useNavigate();

  useEffect(() => {
    if (job?.status === "done" && job.story_id != null) {
      navigate(`/stories/${job.story_id}`, { replace: true });
    }
  }, [job, navigate]);

  useEffect(() => {
    if (job?.status === "error") {
      setError(job.error ?? "Generation failed");
    }
  }, [job]);

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

  const running = jobId !== null && job?.status !== "done" && job?.status !== "error";

  return (
    <div
      className="fixed inset-0 z-10 flex items-center justify-center bg-slate-900/40 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-slate-900">
          {running ? "Generating story" : "Create a new story"}
        </h2>

        {running ? (
          <div className="mt-4 space-y-2">
            <p className="text-sm text-slate-500">
              {job?.stage ?? "queued"}
              {"…"}
            </p>
            <div className="h-2 w-full animate-pulse rounded-full bg-slate-200" />
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-4 space-y-3">
            <label className="block">
              <span className="text-sm font-medium text-slate-700">Topic</span>
              <input
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                placeholder="e.g. Chip demand in 2026"
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                required
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">
                Angle <span className="font-normal text-slate-400">(optional)</span>
              </span>
              <input
                value={angle}
                onChange={(event) => setAngle(event.target.value)}
                placeholder="e.g. key numbers and statistics"
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="block">
              <span className="text-sm font-medium text-slate-700">
                Instructions <span className="font-normal text-slate-400">(optional)</span>
              </span>
              <textarea
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
                rows={3}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <div className="flex justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading || !topic.trim()}
                className="rounded-md bg-blush px-4 py-2 text-sm font-medium text-slate-900 hover:bg-blush-dark disabled:opacity-50"
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
