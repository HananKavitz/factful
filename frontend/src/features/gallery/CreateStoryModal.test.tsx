import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useSyncExternalStore } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { JobStatus } from "../../types";
import { CreateStoryModal } from "./CreateStoryModal";

const jobStore = vi.hoisted(() => {
  let job: JobStatus | null = null;
  const listeners = new Set<() => void>();
  return {
    setJob(next: JobStatus | null) {
      job = next;
      listeners.forEach((listener) => listener());
    },
    getJob: () => job,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
});

const stories = vi.hoisted(() => ({
  createStory: vi.fn(() => ({
    unwrap: () => Promise.resolve({ job_id: "job-1" }),
  })),
}));

vi.mock("../jobs/jobsApi", () => ({
  useGetJobQuery: () => ({
    data: useSyncExternalStore(jobStore.subscribe, jobStore.getJob),
  }),
}));

vi.mock("../stories/storiesApi", () => ({
  useCreateStoryMutation: () => [stories.createStory, { isLoading: false }],
}));

function LocationProbe() {
  const location = useLocation();
  return <p>path={location.pathname}</p>;
}

function renderModal() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route
          path="/"
          element={
            <>
              <CreateStoryModal onClose={() => undefined} />
              <LocationProbe />
            </>
          }
        />
        <Route path="/stories/:id" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("CreateStoryModal", () => {
  beforeEach(() => {
    jobStore.setJob(null);
    stories.createStory.mockClear();
  });

  it("submits the form and navigates to the story when the job completes", async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText("e.g. Chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    expect(stories.createStory).toHaveBeenCalledWith({
      topic: "Chips",
      angle: null,
      instructions: null,
    });

    act(() =>
      jobStore.setJob({
        job_id: "job-1",
        status: "running",
        stage: "research",
        error: null,
        story_id: null,
      }),
    );
    expect(await screen.findByText("Generating story")).toBeInTheDocument();

    act(() =>
      jobStore.setJob({
        job_id: "job-1",
        status: "done",
        stage: "publish",
        error: null,
        story_id: 1,
      }),
    );
    expect(await screen.findByText("path=/stories/1")).toBeInTheDocument();
  });

  it("shows the stage while the job is running", async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText("e.g. Chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    act(() =>
      jobStore.setJob({
        job_id: "job-1",
        status: "running",
        stage: "writing",
        error: null,
        story_id: null,
      }),
    );
    expect(await screen.findByText("writing…")).toBeInTheDocument();
  });

  it("shows the error from a failed job", async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText("e.g. Chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    act(() =>
      jobStore.setJob({
        job_id: "job-1",
        status: "error",
        stage: null,
        error: "LLM provider timed out",
        story_id: null,
      }),
    );
    expect(await screen.findByText("LLM provider timed out")).toBeInTheDocument();
  });

  it("shows an error when creating the job fails", async () => {
    stories.createStory.mockReturnValue({
      unwrap: () => Promise.reject(new Error("boom")),
    });
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText("e.g. Chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    expect(
      await screen.findByText("Could not start generation. Please try again."),
    ).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Create a new story")).toBeInTheDocument());
  });
});
