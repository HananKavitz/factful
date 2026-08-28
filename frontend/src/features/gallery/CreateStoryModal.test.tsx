import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { configureStore } from "@reduxjs/toolkit";
import userEvent from "@testing-library/user-event";
import { useSyncExternalStore } from "react";
import { Provider } from "react-redux";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { baseApi } from "../../app/api";
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

const jobs = vi.hoisted(() => ({
  cancelJob: vi.fn(() => ({
    unwrap: () =>
      Promise.resolve({
        job_id: "job-1",
        status: "cancelled",
        stage: null,
        error: null,
        story_id: null,
        progress: null,
      }),
  })),
}));

const stories = vi.hoisted(() => ({
  createStory: vi.fn(() => ({
    unwrap: () =>
      Promise.resolve({
        job_id: "job-1",
        status: "queued",
        stage: null,
        error: null,
        story_id: null,
        progress: null,
      }),
  })),
}));

vi.mock("../jobs/jobsApi", () => ({
  useGetJobQuery: () => ({
    data: useSyncExternalStore(jobStore.subscribe, jobStore.getJob),
  }),
  useCancelJobMutation: () => [jobs.cancelJob, { isLoading: false }],
}));

vi.mock("../stories/storiesApi", () => ({
  useCreateStoryMutation: () => [stories.createStory, { isLoading: false }],
}));

function LocationProbe() {
  const location = useLocation();
  return <p>path={location.pathname}</p>;
}

function makeStore() {
  const dispatched: unknown[] = [];
  const store = configureStore({
    reducer: { [baseApi.reducerPath]: baseApi.reducer },
    middleware: (getDefaultMiddleware) =>
      getDefaultMiddleware().concat(
        baseApi.middleware,
        () =>
          (next: (action: unknown) => unknown) =>
          (action: unknown) => {
            dispatched.push(action);
            return next(action);
          },
      ),
  });
  return { store, dispatched };
}

function renderModal(
  onClose = () => undefined,
  initialValues?: { prompt: string; angle: string | null; instructions: string | null },
  store = makeStore().store,
) {
  return render(
    <Provider store={store}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route
            path="/"
            element={
              <>
                <CreateStoryModal onClose={onClose} initialValues={initialValues} />
                <LocationProbe />
              </>
            }
          />
          <Route path="/stories/:id" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </Provider>,
  );
}

describe("CreateStoryModal", () => {
  beforeEach(() => {
    jobStore.setJob(null);
    stories.createStory.mockReset();
    stories.createStory.mockImplementation(() => ({
      unwrap: () =>
        Promise.resolve({
          job_id: "job-1",
          status: "queued",
          stage: null,
          error: null,
          story_id: null,
          progress: null,
        }),
    }));
    jobs.cancelJob.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("submits the form and navigates to the story when the job completes", async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText("e.g. Write about chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    expect(stories.createStory).toHaveBeenCalledWith({
      prompt: "Chips",
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
        progress: null,
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
        progress: null,
      }),
    );
    expect(await screen.findByText("path=/stories/1")).toBeInTheDocument();
  });

  it("invalidates the story list when the job completes", async () => {
    const { store, dispatched } = makeStore();
    const user = userEvent.setup();
    renderModal(undefined, undefined, store);

    await user.type(screen.getByPlaceholderText("e.g. Write about chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    act(() =>
      jobStore.setJob({
        job_id: "job-1",
        status: "done",
        stage: "publish",
        error: null,
        story_id: 1,
        progress: null,
      }),
    );
    expect(await screen.findByText("path=/stories/1")).toBeInTheDocument();

    await waitFor(() =>
      expect(dispatched).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: "api/invalidateTags",
            payload: expect.arrayContaining([
              expect.objectContaining({ type: "Story", id: "LIST" }),
            ]),
          }),
        ]),
      ),
    );
  });

  it("shows the stage while the job is running", async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText("e.g. Write about chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    act(() =>
      jobStore.setJob({
        job_id: "job-1",
        status: "running",
        stage: "writing",
        error: null,
        story_id: null,
        progress: null,
      }),
    );
    expect(await screen.findByText("writing…")).toBeInTheDocument();
  });

  it("shows a determinate progress bar when progress is reported", async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText("e.g. Write about chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    act(() =>
      jobStore.setJob({
        job_id: "job-1",
        status: "running",
        stage: "fact-checking",
        error: null,
        story_id: null,
        progress: 57,
      }),
    );
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-valuenow")).toBe("57");
  });

  it("shows the error from a failed job", async () => {
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText("e.g. Write about chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    act(() =>
      jobStore.setJob({
        job_id: "job-1",
        status: "error",
        stage: null,
        error: "LLM provider timed out",
        story_id: null,
        progress: null,
      }),
    );
    expect(await screen.findByText("LLM provider timed out")).toBeInTheDocument();
  });

  it("shows an error when creating the job fails", async () => {
    stories.createStory.mockImplementation(() => ({
      unwrap: () => Promise.reject(new Error("boom")),
    }));
    const user = userEvent.setup();
    renderModal();

    await user.type(screen.getByPlaceholderText("e.g. Write about chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    expect(
      await screen.findByText("Could not start generation. Please try again."),
    ).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Create a new story")).toBeInTheDocument());
  });

  it("focuses the topic input on open", () => {
    renderModal();
    expect(screen.getByPlaceholderText("e.g. Write about chip demand in 2026")).toHaveFocus();
  });

  it("closes on Escape when not running", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderModal(onClose);

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not close on Escape or a backdrop click while running", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { container } = renderModal(onClose);

    await user.type(screen.getByPlaceholderText("e.g. Write about chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));
    act(() =>
      jobStore.setJob({
        job_id: "job-1",
        status: "running",
        stage: "research",
        error: null,
        story_id: null,
        progress: null,
      }),
    );

    await user.keyboard("{Escape}");
    fireEvent.click(container.firstChild as Element);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes on a backdrop click when not running", () => {
    const onClose = vi.fn();
    const { container } = renderModal(onClose);

    fireEvent.mouseDown(container.firstChild as Element);
    fireEvent.click(container.firstChild as Element);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not close when selecting text in the topic input and releasing on the backdrop", () => {
    const onClose = vi.fn();
    const { container } = renderModal(onClose);
    const backdrop = container.firstChild as Element;
    const textarea = screen.getByPlaceholderText("e.g. Write about chip demand in 2026");

    fireEvent.mouseDown(textarea);
    fireEvent.mouseUp(backdrop);
    fireEvent.click(backdrop);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("keeps the modal open while pasting into the topic input", () => {
    const onClose = vi.fn();
    renderModal(onClose);

    const textarea = screen.getByPlaceholderText("e.g. Write about chip demand in 2026");
    fireEvent.change(textarea, { target: { value: "Chip demand in 2026" } });

    expect(onClose).not.toHaveBeenCalled();
    expect(textarea).toHaveValue("Chip demand in 2026");
  });

  it("shows an elapsed clock while the job is running", async () => {
    vi.useFakeTimers();
    renderModal();

    fireEvent.change(screen.getByPlaceholderText("e.g. Write about chip demand in 2026"), {
      target: { value: "Chips" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    await act(async () => {
      vi.advanceTimersByTime(0);
    });
    act(() =>
      jobStore.setJob({
        job_id: "job-1",
        status: "running",
        stage: "research",
        error: null,
        story_id: null,
        progress: null,
      }),
    );

    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(screen.getByText("00:01")).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(9000);
    });
    expect(screen.getByText("00:10")).toBeInTheDocument();
  });

  it("stops the run and closes the modal", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderModal(onClose);

    await user.type(screen.getByPlaceholderText("e.g. Write about chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));
    act(() =>
      jobStore.setJob({
        job_id: "job-1",
        status: "running",
        stage: "research",
        error: null,
        story_id: null,
        progress: null,
      }),
    );

    await user.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
    expect(jobs.cancelJob).toHaveBeenCalledWith("job-1");
  });

  it("closes the modal when the job is cancelled", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderModal(onClose);

    await user.type(screen.getByPlaceholderText("e.g. Write about chip demand in 2026"), "Chips");
    await user.click(screen.getByRole("button", { name: "Generate" }));
    act(() =>
      jobStore.setJob({
        job_id: "job-1",
        status: "cancelled",
        stage: null,
        error: null,
        story_id: null,
        progress: null,
      }),
    );

    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("pre-fills the form and shows the regenerate heading when initialValues are provided", () => {
    renderModal(undefined, {
      prompt: "Chip demand in 2026",
      angle: "key numbers and statistics",
      instructions: "Keep it under 800 words.",
    });

    expect(
      screen.getByRole("heading", { name: "Regenerate story" }),
    ).toBeInTheDocument();
    expect(screen.getByPlaceholderText("e.g. Write about chip demand in 2026")).toHaveValue(
      "Chip demand in 2026",
    );
    expect(screen.getByPlaceholderText("e.g. key numbers and statistics")).toHaveValue(
      "key numbers and statistics",
    );
    expect(screen.getByDisplayValue("Keep it under 800 words.")).toBeInTheDocument();
  });

  it("submits the pre-filled values unchanged when untouched", async () => {
    const user = userEvent.setup();
    renderModal(undefined, {
      prompt: "Chip demand in 2026",
      angle: "key numbers and statistics",
      instructions: "Keep it under 800 words.",
    });

    await user.click(screen.getByRole("button", { name: "Generate" }));

    expect(stories.createStory).toHaveBeenCalledWith({
      prompt: "Chip demand in 2026",
      angle: "key numbers and statistics",
      instructions: "Keep it under 800 words.",
    });
  });

  it("submits the edited value when a pre-filled field is changed", async () => {
    const user = userEvent.setup();
    renderModal(undefined, {
      prompt: "Chip demand in 2026",
      angle: "key numbers and statistics",
      instructions: null,
    });

    const prompt = screen.getByPlaceholderText("e.g. Write about chip demand in 2026");
    await user.clear(prompt);
    await user.type(prompt, "AI chip demand");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    expect(stories.createStory).toHaveBeenCalledWith({
      prompt: "AI chip demand",
      angle: "key numbers and statistics",
      instructions: null,
    });
  });
});
