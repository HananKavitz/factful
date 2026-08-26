interface NoteModalProps {
  instructions: string;
  generatedNote: string | null;
  onInstructionsChange: (text: string) => void;
  onGenerate: () => void;
  onClose: () => void;
  onCopy: (text: string) => void;
  onNoteChange: (text: string) => void;
  loading: boolean;
  error: string | null;
}

export function NoteModal({
  instructions,
  generatedNote,
  onInstructionsChange,
  onGenerate,
  onClose,
  onCopy,
  onNoteChange,
  loading,
  error,
}: NoteModalProps) {
  const isGenerating = loading && generatedNote === null;

  return (
    <div
      className="fixed inset-0 z-10 flex items-center justify-center bg-slate-900/40 px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-slate-900">Substack Note</h2>

        {isGenerating && (
          <div className="mt-4 flex items-center gap-2 text-sm text-slate-500">
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
            <span>Generating note…</span>
          </div>
        )}

        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

        {!loading && generatedNote === null && (
          <>
            <label className="mt-4 block">
              <span className="text-sm font-medium text-slate-700">
                Instructions (optional)
              </span>
              <textarea
                value={instructions}
                onChange={(event) => onInstructionsChange(event.target.value)}
                rows={3}
                placeholder="e.g. Keep it under 20 words and make it funny."
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-400 focus:outline-none"
              />
            </label>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={onGenerate}
                disabled={loading}
                className="rounded-md bg-blush px-4 py-2 text-sm font-medium text-slate-900 hover:bg-blush-dark disabled:opacity-50"
              >
                Generate note
              </button>
            </div>
          </>
        )}

        {!loading && generatedNote !== null && (
          <>
            <textarea
              value={generatedNote}
              onChange={(event) => onNoteChange(event.target.value)}
              rows={5}
              className="mt-4 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-400 focus:outline-none"
              aria-label="Substack Note text"
            />
            <p className="mt-1 text-xs text-slate-400">
              Edit the note before copying, then paste it into Substack Notes.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={onClose}
                className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
              <button
                type="button"
                onClick={() => onCopy(generatedNote)}
                className="rounded-md bg-blush px-4 py-2 text-sm font-medium text-slate-900 hover:bg-blush-dark"
              >
                Copy
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}