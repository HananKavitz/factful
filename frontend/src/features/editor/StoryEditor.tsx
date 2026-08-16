import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  useDeleteStoryMutation,
  useEditStoryMutation,
  useGetStoryQuery,
  useUpdateStoryMutation,
} from "../stories/storiesApi";
import type { StoryDetail } from "../../types";

const SAVE_DELAY_MS = 800;

export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}

const inputClass =
  "w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-400 focus:outline-none";

export function StoryEditor() {
  const { storyId } = useParams();
  const id = Number(storyId);
  const { data: story, isLoading } = useGetStoryQuery(id);

  if (isLoading) {
    return <p className="text-slate-400">Loading…</p>;
  }

  if (!story) {
    return <p className="text-slate-500">Story not found.</p>;
  }

  return <EditorForm key={story.id} story={story} />;
}

interface EditorFormProps {
  story: StoryDetail;
}

function EditorForm({ story }: EditorFormProps) {
  const [updateStory, { isLoading: saving }] = useUpdateStoryMutation();
  const [editStory, { isLoading: editing }] = useEditStoryMutation();
  const [deleteStory, { isLoading: deleting }] = useDeleteStoryMutation();
  const navigate = useNavigate();

  const [title, setTitle] = useState(story.title);
  const [markdown, setMarkdown] = useState(story.markdown);
  const [prompt, setPrompt] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const debouncedTitle = useDebouncedValue(title, SAVE_DELAY_MS);
  const debouncedMarkdown = useDebouncedValue(markdown, SAVE_DELAY_MS);

  useEffect(() => {
    if (debouncedTitle === story.title && debouncedMarkdown === story.markdown) {
      return;
    }
    updateStory({
      id: story.id,
      body: { title: debouncedTitle, markdown: debouncedMarkdown },
    })
      .unwrap()
      .then(() => setSaveError(null))
      .catch(() => setSaveError("Autosave failed. Check your connection."));
  }, [debouncedTitle, debouncedMarkdown, story, updateStory]);

  const handlePromptEdit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!prompt.trim()) return;
    try {
      const result = await editStory({ id: story.id, body: { prompt: prompt.trim() } }).unwrap();
      setTitle(result.title);
      setMarkdown(result.markdown);
      setPrompt("");
    } catch {
      setSaveError("Edit failed. Please try again.");
    }
  };

  const handleDelete = async () => {
    try {
      await deleteStory(story.id).unwrap();
      navigate("/");
    } catch {
      setSaveError("Delete failed. Please try again.");
      setConfirmOpen(false);
    }
  };

  const wordCount = markdown.trim() ? markdown.trim().split(/\s+/).length : 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">{story.topic}</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400">
            {saving ? "Saving…" : saveError ?? "Saved"}
          </span>
          <button
            onClick={() => setConfirmOpen(true)}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Delete
          </button>
        </div>
      </div>

      {confirmOpen && (
        <div
          className="fixed inset-0 z-10 flex items-center justify-center bg-slate-900/40 px-4"
          onClick={() => setConfirmOpen(false)}
        >
          <div
            className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 className="text-lg font-semibold text-slate-900">Delete this story?</h2>
            <p className="mt-2 text-sm text-slate-500">
              This action is permanent and can't be undone.
            </p>
            {saveError && <p className="mt-2 text-sm text-red-600">{saveError}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfirmOpen(false)}
                className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deleting ? "Deleting…" : "Confirm delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      <input
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        placeholder="Title"
        className={inputClass}
      />

      <textarea
        value={markdown}
        onChange={(event) => setMarkdown(event.target.value)}
        rows={24}
        className={`${inputClass} font-mono text-xs leading-relaxed`}
      />
      <div className="-mt-3 flex justify-end">
        <span className="text-xs text-slate-400">
          {wordCount} {wordCount === 1 ? "word" : "words"}
        </span>
      </div>

      <form
        onSubmit={handlePromptEdit}
        className="rounded-lg border border-slate-200 bg-white p-4"
      >
        <label className="block">
          <span className="text-sm font-medium text-slate-700">
            Ask for an edit
          </span>
          <textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            rows={2}
            placeholder="e.g. Shorten the lead to one sentence"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <div className="mt-2 flex justify-end">
          <button
            type="submit"
            disabled={editing || !prompt.trim()}
            className="rounded-md bg-blush px-4 py-2 text-sm font-medium text-slate-900 hover:bg-blush-dark disabled:opacity-50"
          >
            {editing ? "Editing…" : "Apply edit"}
          </button>
        </div>
      </form>
    </div>
  );
}
