import { useState } from "react";
import { Link } from "react-router-dom";
import { CreateStoryModal } from "./CreateStoryModal";
import { useListStoriesQuery } from "../stories/storiesApi";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function Gallery() {
  const { data: stories, isLoading } = useListStoriesQuery();
  const [open, setOpen] = useState(false);

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">Stories</h1>
        <button
          onClick={() => setOpen(true)}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          Create new story
        </button>
      </div>

      {isLoading && <p className="mt-6 text-slate-400">Loading…</p>}
      {stories && stories.length === 0 && (
        <p className="mt-6 text-slate-500">
          No stories yet. Create your first one.
        </p>
      )}

      <ul className="mt-6 space-y-3">
        {stories?.map((story) => (
          <li key={story.id}>
            <Link
              to={`/stories/${story.id}`}
              className="block rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:border-slate-300"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-900">{story.title}</span>
                <span className="text-xs text-slate-400">
                  {formatDate(story.created_at)}
                </span>
              </div>
              <p className="mt-1 text-sm text-slate-500">
                {story.topic}
                {story.score != null && ` · score ${Math.round(story.score)}`}
              </p>
            </Link>
          </li>
        ))}
      </ul>

      {open && <CreateStoryModal onClose={() => setOpen(false)} />}
    </div>
  );
}
