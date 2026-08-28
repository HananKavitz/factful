import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  useDeleteStoryMutation,
  useEditStoryMutation,
  useGenerateNoteMutation,
  useGetStoryQuery,
  useRenderVideoMutation,
  useUpdateStoryMutation,
} from "../stories/storiesApi";
import { useGetJobQuery } from "../jobs/jobsApi";
import { CreateStoryModal } from "../gallery/CreateStoryModal";
import { NoteModal } from "./NoteModal";
import { VideoTab } from "./VideoTab";
import type { StoryDetail } from "../../types";

const SAVE_DELAY_MS = 800;
const VIDEO_POLL_INTERVAL_MS = 2000;

type TabId = "story" | "video";

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
  const [generateNote, { isLoading: generatingNote }] = useGenerateNoteMutation();
  const [renderVideo, { isLoading: renderingVideo }] = useRenderVideoMutation();
  const navigate = useNavigate();

  const [title, setTitle] = useState(story.title);
  const [markdown, setMarkdown] = useState(story.markdown);
  const [prompt, setPrompt] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [regenerateOpen, setRegenerateOpen] = useState(false);
  const [noteModalOpen, setNoteModalOpen] = useState(false);
  const [generatedNote, setGeneratedNote] = useState<string | null>(null);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [noteInstructions, setNoteInstructions] = useState("");
  const [activeTab, setActiveTab] = useState<TabId>("story");

  // Video state
  const [videoJobId, setVideoJobId] = useState<string | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);
  const [selectedVideoId, setSelectedVideoId] = useState<number | null>(null);
  const [selectedVoice, setSelectedVoice] = useState(
    // Default to the last used voice if there's a playable video
    (story.videos ?? []).find((v) => v.status === "completed")?.voice ?? "en-US-AriaNeural"
  );

  const { data: videoJob } = useGetJobQuery(videoJobId ?? "", {
    skip: !videoJobId,
    pollingInterval: VIDEO_POLL_INTERVAL_MS,
  });

  const playableVideos = (story.videos ?? []).filter(
    (v) => v.status === "completed" && v.file_exists
  );

  const hasPlayable = playableVideos.length > 0;
  const selectedVideo = hasPlayable
    ? playableVideos.find((v) => v.id === selectedVideoId) ?? playableVideos[0]
    : null;

  // Auto-select first playable video
  useEffect(() => {
    if (hasPlayable && !selectedVideoId) {
      setSelectedVideoId(playableVideos[0].id);
    }
  }, [hasPlayable, playableVideos, selectedVideoId]);

  // Handle job completion
  useEffect(() => {
    if (!videoJob) return;
    if (videoJob.status === "done") {
      setVideoJobId(null);
      setVideoError(null);
    } else if (videoJob.status === "error") {
      setVideoJobId(null);
      setVideoError(videoJob.error ?? "Video rendering failed.");
    } else if (videoJob.status === "cancelled") {
      setVideoJobId(null);
      setVideoError("Video rendering was cancelled.");
    }
  }, [videoJob]);

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

  const handleOpenNoteModal = () => {
    setNoteModalOpen(true);
    setGeneratedNote(null);
    setNoteError(null);
    setNoteInstructions("");
  };

  const handleGenerateNote = async () => {
    setGeneratedNote(null);
    setNoteError(null);
    try {
      const result = await generateNote({
        id: story.id,
        body: {
          title,
          markdown,
          instructions: noteInstructions.trim() || null,
        },
      }).unwrap();
      setGeneratedNote(result.note);
    } catch {
      setNoteError("Could not generate note. Please try again.");
    }
  };

  const handleCopyNote = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard unavailable — user can manually select and copy
    }
  };

  const handleRenderVideo = useCallback(async () => {
    setVideoError(null);
    setVideoJobId(null);
    try {
      const job = await renderVideo({ id: story.id, body: { voice: selectedVoice } }).unwrap();
      setVideoJobId(job.job_id);
    } catch {
      setVideoError("Failed to start video render.");
    }
  }, [story.id, renderVideo, selectedVoice]);

  const wordCount = markdown.trim() ? markdown.trim().split(/\s+/).length : 0;

  const isRendering =
    renderingVideo ||
    (videoJob !== undefined &&
      (videoJob.status === "queued" || videoJob.status === "running"));

  return (
    <div className="flex h-full flex-col space-y-4">
      <div className="flex shrink-0 items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">{story.topic}</h1>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-400">
            {saving ? "Saving…" : saveError ?? "Saved"}
          </span>
          <button
            onClick={() => setRegenerateOpen(true)}
            className="rounded-md bg-blush px-4 py-2 text-sm font-medium text-slate-900 hover:bg-blush-dark"
          >
            Regenerate
          </button>
          <button
            onClick={handleOpenNoteModal}
            disabled={generatingNote}
            className="rounded-md bg-blush px-4 py-2 text-sm font-medium text-slate-900 hover:bg-blush-dark disabled:opacity-50"
          >
            {generatingNote ? "Generating note…" : "Generate Note"}
          </button>
          <button
            onClick={() => setConfirmOpen(true)}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
          >
            Delete
          </button>
        </div>
      </div>

      {/* Tab bar — common to all tabs */}
      <div className="flex shrink-0 border-b border-slate-200">
        <button
          onClick={() => setActiveTab("story")}
          className={`px-4 py-2 text-sm font-medium ${
            activeTab === "story"
              ? "border-b-2 border-slate-900 text-slate-900"
              : "text-slate-500 hover:text-slate-700"
          }`}
        >
          Story
        </button>
        <button
          onClick={() => setActiveTab("video")}
          className={`px-4 py-2 text-sm font-medium ${
            activeTab === "video"
              ? "border-b-2 border-slate-900 text-slate-900"
              : "text-slate-500 hover:text-slate-700"
          }`}
        >
          Video
        </button>
      </div>

      {regenerateOpen && (
        <CreateStoryModal
          initialValues={{
            topic: story.topic,
            angle: story.angle,
            instructions: story.instructions,
          }}
          onClose={() => setRegenerateOpen(false)}
        />
      )}

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

      {noteModalOpen && (
        <NoteModal
          instructions={noteInstructions}
          generatedNote={generatedNote}
          onInstructionsChange={setNoteInstructions}
          onGenerate={handleGenerateNote}
          onClose={() => setNoteModalOpen(false)}
          onCopy={handleCopyNote}
          onNoteChange={setGeneratedNote}
          loading={generatingNote}
          error={noteError}
        />
      )}

      {activeTab === "story" && (
        <>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Title"
            className={`${inputClass} shrink-0`}
          />

          <textarea
            value={markdown}
            onChange={(event) => setMarkdown(event.target.value)}
            className={`${inputClass} min-h-0 flex-1 resize-none font-mono text-xs leading-relaxed`}
          />
          <div className="-mt-3 flex shrink-0 justify-end">
            <span className="text-xs text-slate-400">
              {wordCount} {wordCount === 1 ? "word" : "words"}
            </span>
          </div>

          <form
            onSubmit={handlePromptEdit}
            className="shrink-0 rounded-lg border border-slate-200 bg-white p-4"
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
                className="inline-flex items-center gap-2 rounded-md bg-blush px-4 py-2 text-sm font-medium text-slate-900 hover:bg-blush-dark disabled:opacity-50"
              >
                {editing && (
                  <svg
                    className="h-4 w-4 animate-spin"
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
                    />
                  </svg>
                )}
                {editing ? "Editing…" : "Apply edit"}
              </button>
            </div>
          </form>
        </>
      )}

      {activeTab === "video" && (
        <VideoTab
          voice={selectedVoice}
          onVoiceChange={setSelectedVoice}
          playableVideos={playableVideos}
          selectedVideo={selectedVideo}
          selectedVideoId={selectedVideoId}
          onSelectedVideoIdChange={setSelectedVideoId}
          hasPlayable={hasPlayable}
          videos={story.videos ?? []}
          isRendering={isRendering}
          onRenderVideo={handleRenderVideo}
          videoError={videoError}
        />
      )}
    </div>
  );
}
