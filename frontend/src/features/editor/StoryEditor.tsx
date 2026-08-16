import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useEditStoryMutation, useGetStoryQuery, useUpdateStoryMutation } from "../stories/storiesApi";
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

  const [title, setTitle] = useState(story.title);
  const [markdown, setMarkdown] = useState(story.markdown);
  const [prompt, setPrompt] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);

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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">{story.topic}</h1>
        <span className="text-xs text-slate-400">
          {saving ? "Saving…" : saveError ?? "Saved"}
        </span>
      </div>

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
