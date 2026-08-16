import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { StoryDetail } from "../../types";

const hooks = vi.hoisted(() => ({
  story: null as StoryDetail | null,
  saving: false,
  editing: false,
  updateStory: vi.fn(() => ({
    unwrap: () => Promise.resolve(hooks.story),
  })),
  editStory: vi.fn(() => ({
    unwrap: () => Promise.resolve(hooks.story),
  })),
}));

vi.mock("../stories/storiesApi", () => ({
  useGetStoryQuery: () => ({
    data: hooks.story,
    isLoading: hooks.story === null,
  }),
  useUpdateStoryMutation: () => [hooks.updateStory, { isLoading: hooks.saving }],
  useEditStoryMutation: () => [hooks.editStory, { isLoading: hooks.editing }],
}));

import { StoryEditor } from "./StoryEditor";

const story: StoryDetail = {
  id: 1,
  title: "Chips",
  topic: "Semiconductors",
  score: 88,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  angle: null,
  instructions: null,
  markdown: "# Chips\n\nDemand is rising.",
};

function renderEditor() {
  return render(
    <MemoryRouter initialEntries={["/stories/1"]}>
      <Routes>
        <Route path="/stories/:storyId" element={<StoryEditor />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("StoryEditor", () => {
  beforeEach(() => {
    hooks.story = story;
    hooks.saving = false;
    hooks.editing = false;
    hooks.updateStory.mockClear();
    hooks.editStory.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows a loading state before the story arrives", () => {
    hooks.story = null;
    renderEditor();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("autosaves title and markdown after the debounce delay", async () => {
    vi.useFakeTimers();
    renderEditor();

    const titleInput = screen.getByDisplayValue("Chips");
    fireEvent.change(titleInput, { target: { value: "New title" } });
    expect(hooks.updateStory).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(800);
    });
    expect(hooks.updateStory).toHaveBeenCalledWith({
      id: 1,
      body: { title: "New title", markdown: "# Chips\n\nDemand is rising." },
    });
  });

  it("does not autosave when nothing changed", () => {
    vi.useFakeTimers();
    renderEditor();
    act(() => {
      vi.advanceTimersByTime(800);
    });
    expect(hooks.updateStory).not.toHaveBeenCalled();
  });

  it("shows saving state while an autosave is in flight", async () => {
    vi.useFakeTimers();
    hooks.saving = true;
    renderEditor();

    const titleInput = screen.getByDisplayValue("Chips");
    fireEvent.change(titleInput, { target: { value: "New title" } });

    await act(async () => {
      vi.advanceTimersByTime(800);
    });
    expect(screen.getByText("Saving…")).toBeInTheDocument();
  });

  it("applies a prompt edit and updates the local draft", async () => {
    hooks.editStory.mockReturnValue({
      unwrap: () =>
        Promise.resolve({ ...story, title: "Chips 2", markdown: "# Chips 2\n\nNew." }),
    });
    renderEditor();

    const user = userEvent.setup();
    const prompt = screen.getByPlaceholderText("e.g. Shorten the lead to one sentence");
    await user.type(prompt, "Shorten the lead");
    await user.click(screen.getByRole("button", { name: "Apply edit" }));

    await waitFor(() => {
      expect(screen.getByDisplayValue(/Chips 2\s+New\./)).toBeInTheDocument();
    });
    expect(hooks.editStory).toHaveBeenCalledWith({
      id: 1,
      body: { prompt: "Shorten the lead" },
    });
    expect(screen.getByDisplayValue("Chips 2")).toBeInTheDocument();
    expect(
      (screen.getByPlaceholderText("e.g. Shorten the lead to one sentence") as HTMLTextAreaElement)
        .value,
    ).toBe("");
  });

  it("does not submit an empty prompt", () => {
    renderEditor();
    const button = screen.getByRole("button", { name: "Apply edit" });
    expect(button).toBeDisabled();
  });

  it("shows a live word count for the markdown", async () => {
    renderEditor();
    const editor = screen.getByDisplayValue(/^# Chips\s+Demand is rising\.\s*$/);
    expect(screen.getByText("5 words")).toBeInTheDocument();

    const user = userEvent.setup();
    await user.clear(editor);
    expect(screen.getByText("0 words")).toBeInTheDocument();
  });
});
