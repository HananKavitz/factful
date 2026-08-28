import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { configureStore } from "@reduxjs/toolkit";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { baseApi } from "../../app/api";
import type { StoryDetail } from "../../types";

const hooks = vi.hoisted(() => ({
  story: null as StoryDetail | null,
  saving: false,
  editing: false,
  deleting: false,
  generatingNote: false,
  renderingVideo: false,
  generatedNote: null as string | null,
  updateStory: vi.fn(() => ({
    unwrap: () => Promise.resolve(hooks.story),
  })),
  editStory: vi.fn(() => ({
    unwrap: () => Promise.resolve(hooks.story),
  })),
  deleteStory: vi.fn(() => ({
    unwrap: () => Promise.resolve(undefined),
  })),
  createStory: vi.fn(() => ({
    unwrap: () => Promise.resolve({ job_id: "job-1" }),
  })),
  cancelJob: vi.fn(() => ({
    unwrap: () => Promise.resolve(undefined),
  })),
  generateNote: vi.fn(() => ({
    unwrap: () => Promise.resolve({ note: hooks.generatedNote ?? "Check out this story!" }),
  })),
  renderVideo: vi.fn(() => ({
    unwrap: () => Promise.resolve({ job_id: "video-job-1" }),
  })),
}));

vi.mock("../stories/storiesApi", () => ({
  useGetStoryQuery: () => ({
    data: hooks.story,
    isLoading: hooks.story === null,
  }),
  useUpdateStoryMutation: () => [hooks.updateStory, { isLoading: hooks.saving }],
  useEditStoryMutation: () => [hooks.editStory, { isLoading: hooks.editing }],
  useDeleteStoryMutation: () => [hooks.deleteStory, { isLoading: hooks.deleting }],
  useCreateStoryMutation: () => [hooks.createStory, { isLoading: false }],
  useGenerateNoteMutation: () => [hooks.generateNote, { isLoading: hooks.generatingNote }],
  useRenderVideoMutation: () => [hooks.renderVideo, { isLoading: hooks.renderingVideo }],
}));

vi.mock("../jobs/jobsApi", () => ({
  useGetJobQuery: () => ({ data: undefined }),
  useCancelJobMutation: () => [hooks.cancelJob, { isLoading: false }],
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
  videos: [],
};

function renderEditor() {
  const store = configureStore({
    reducer: { [baseApi.reducerPath]: baseApi.reducer },
    middleware: (getDefaultMiddleware) =>
      getDefaultMiddleware().concat(baseApi.middleware),
  });
  return render(
    <Provider store={store}>
      <MemoryRouter initialEntries={["/stories/1"]}>
        <Routes>
          <Route path="/stories/:storyId" element={<StoryEditor />} />
          <Route path="/" element={<p>gallery page</p>} />
        </Routes>
      </MemoryRouter>
    </Provider>,
  );
}

describe("StoryEditor", () => {
  beforeEach(() => {
    hooks.story = story;
    hooks.saving = false;
    hooks.editing = false;
    hooks.deleting = false;
    hooks.generatingNote = false;
    hooks.generatedNote = null;
    hooks.updateStory.mockReset();
    hooks.editStory.mockReset();
    hooks.deleteStory.mockReset();
    hooks.generateNote.mockReset();
    hooks.generateNote.mockReturnValue({
      unwrap: () => Promise.resolve({ note: hooks.generatedNote ?? "Check out this story!" }),
    });
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

  it("shows a spinner on the edit button while an edit is in flight", () => {
    hooks.editing = true;
    const { container } = renderEditor();
    expect(screen.getByText("Editing…")).toBeInTheDocument();
    expect(container.querySelector(".animate-spin")).not.toBeNull();
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

  it("opens a confirm dialog before deleting and cancels without deleting", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(
      screen.getByText("Delete this story?"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(hooks.deleteStory).not.toHaveBeenCalled();
    expect(screen.queryByText("Delete this story?")).not.toBeInTheDocument();
  });

  it("shows the Story tab by default", () => {
    renderEditor();
    const storyTab = screen.getByRole("button", { name: "Story" });
    const videoTab = screen.getByRole("button", { name: "Video" });

    expect(storyTab.className).toContain("border-slate-900");
    expect(videoTab.className).not.toContain("border-slate-900");
    expect(screen.getByPlaceholderText("Title")).toBeInTheDocument();
  });

  it("switches to the Video tab when clicked", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Video" }));

    const storyTab = screen.getByRole("button", { name: "Story" });
    const videoTab = screen.getByRole("button", { name: "Video" });

    expect(videoTab.className).toContain("border-slate-900");
    expect(storyTab.className).not.toContain("border-slate-900");
    expect(screen.getByText("Video Generation")).toBeInTheDocument();
  });

  it("hides the story editor when switching to the Video tab", async () => {
    const user = userEvent.setup();
    renderEditor();

    expect(screen.getByPlaceholderText("Title")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Video" }));

    expect(screen.queryByPlaceholderText("Title")).not.toBeInTheDocument();
  });

  it("switches back to the Story tab from the Video tab", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Video" }));
    expect(screen.getByText("Video Generation")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Story" }));
    expect(screen.getByPlaceholderText("Title")).toBeInTheDocument();
  });

  it("renders the Render Video button in the Video tab when there are no videos", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Video" }));
    expect(
      screen.getByRole("button", { name: "Render Video" }),
    ).toBeInTheDocument();
  });

  it("renders the video player in the Video tab when playable videos exist", async () => {
    hooks.story = {
      ...story,
      videos: [
        {
          id: 1,
          url: "https://example.com/video.mp4",
          voice: "en-US-AriaNeural",
          duration_seconds: 120,
          file_size_bytes: 5_000_000,
          resolution: "1920x1080",
          status: "completed",
          error_message: null,
          file_exists: true,
          created_at: "2026-01-01T00:00:00Z",
        },
      ],
    };
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Video" }));
    // The tab button also says "Video", so use the heading inside the video player card
    expect(screen.getByRole("heading", { name: "Video" })).toBeInTheDocument();
    const videoElement = document.querySelector("video");
    expect(videoElement).not.toBeNull();
    expect(videoElement!.getAttribute("src")).toBe("https://example.com/video.mp4");
  });

  it("deletes the story and navigates to the gallery", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Confirm delete" }));

    await waitFor(() => {
      expect(hooks.deleteStory).toHaveBeenCalledWith(1);
    });
    expect(await screen.findByText("gallery page")).toBeInTheDocument();
  });

  it("opens the regenerate modal pre-filled with the story's saved prompts", async () => {
    hooks.story = {
      ...story,
      angle: "key numbers",
      instructions: "Keep it under 800 words.",
    };
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Regenerate" }));

    expect(
      screen.getByRole("heading", { name: "Regenerate story" }),
    ).toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. Chip demand in 2026")).toHaveValue(
      "Semiconductors",
    );
    expect(screen.getByPlaceholderText("e.g. key numbers and statistics")).toHaveValue(
      "key numbers",
    );
    expect(screen.getByDisplayValue("Keep it under 800 words.")).toBeInTheDocument();
  });

  it("closes the regenerate modal when cancelled", async () => {
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Regenerate" }));
    expect(
      screen.getByRole("heading", { name: "Regenerate story" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(
      screen.queryByRole("heading", { name: "Regenerate story" }),
    ).not.toBeInTheDocument();
  });

  it("shows a Generate Note button", () => {
    renderEditor();
    expect(screen.getByRole("button", { name: "Generate Note" })).toBeInTheDocument();
  });

  it("opens the note modal and lets the user inject instructions", async () => {
    hooks.generatedNote = "Check out this amazing story!";
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Generate Note" }));

    expect(hooks.generateNote).not.toHaveBeenCalled();
    const instructions = screen.getByLabelText("Instructions (optional)");
    await user.type(instructions, "Keep it under 20 words.");

    await user.click(screen.getByRole("button", { name: "Generate note" }));

    expect(hooks.generateNote).toHaveBeenCalledWith({
      id: 1,
      body: {
        title: "Chips",
        markdown: "# Chips\n\nDemand is rising.",
        instructions: "Keep it under 20 words.",
      },
    });
    const noteTextarea = await screen.findByLabelText("Substack Note text");
    expect(noteTextarea).toHaveValue("Check out this amazing story!");
    expect(screen.getByText("Substack Note")).toBeInTheDocument();
  });

  it("generates with no instructions when the field is left blank", async () => {
    hooks.generatedNote = "Check out this amazing story!";
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Generate Note" }));
    await user.click(screen.getByRole("button", { name: "Generate note" }));

    expect(hooks.generateNote).toHaveBeenCalledWith({
      id: 1,
      body: {
        title: "Chips",
        markdown: "# Chips\n\nDemand is rising.",
        instructions: null,
      },
    });
    await screen.findByLabelText("Substack Note text");
  });

  it("shows a loading state while generating", async () => {
    hooks.generatingNote = false;
    hooks.generateNote.mockReturnValue({
      unwrap: () => new Promise(() => {}),
    });
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Generate Note" }));
    hooks.generatingNote = true;
    await user.type(screen.getByLabelText("Instructions (optional)"), "x");

    expect(screen.getAllByText("Generating note…").length).toBeGreaterThan(0);
  });

  it("shows an error in the modal when generation fails", async () => {
    hooks.generateNote.mockReturnValue({
      unwrap: () => Promise.reject(new Error("Network error")),
    });
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Generate Note" }));
    await user.click(screen.getByRole("button", { name: "Generate note" }));

    expect(await screen.findByText("Could not generate note. Please try again.")).toBeInTheDocument();
  });

  it("allows editing the note text before copying", async () => {
    hooks.generatedNote = "Original note text";
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Generate Note" }));
    await user.click(screen.getByRole("button", { name: "Generate note" }));
    const noteTextarea = await screen.findByLabelText("Substack Note text");
    expect(noteTextarea).toHaveValue("Original note text");

    await user.clear(noteTextarea);
    await user.type(noteTextarea, "Edited note text");
    expect(noteTextarea).toHaveValue("Edited note text");
  });

  it("dismisses the note modal when Close is clicked", async () => {
    hooks.generatedNote = "Original note text";
    const user = userEvent.setup();
    renderEditor();

    await user.click(screen.getByRole("button", { name: "Generate Note" }));
    await user.click(screen.getByRole("button", { name: "Generate note" }));
    expect(await screen.findByText("Substack Note")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByText("Substack Note")).not.toBeInTheDocument();
  });
});
