import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StyleProfile } from "../types";
import { Settings } from "./Settings";

const getSettings = vi.hoisted(() => vi.fn());
const saveStyle = vi.hoisted(() => vi.fn());
const clearStyle = vi.hoisted(() => vi.fn());
const updateGeneration = vi.hoisted(() => vi.fn());

vi.mock("../features/settings/settingsApi", () => ({
  useGetSettingsQuery: () => getSettings(),
  useSaveStyleMutation: () => [saveStyle, { isLoading: false }],
  useClearStyleMutation: () => [clearStyle, { isLoading: false }],
  useUpdateGenerationMutation: () => [updateGeneration, { isLoading: false }],
}));

const profile: StyleProfile = {
  name: "my-voice",
  metrics: {
    avg_sentence_words: 16,
    avg_paragraph_sentences: 3,
    paragraph_length_dist: [3],
    numeric_density: 0.4,
  },
  extraction: {
    voice: "wry, long-form",
    tone: "acerbic, skeptical",
    hook_patterns: ["question", "direct-address"],
    story_beats: [],
    transitions: ["on the other hand"],
    rhetorical_devices: [{ label: "rhetorical-question", count: 5, excerpt: "Why? Why not?" }],
    direct_address: [],
    characterization: [],
    opinion_hedges: [],
    comparatives: [],
    modals: [],
    numeric_style: "hundreds of billions",
    cta_style: null,
    signoff_style: "Yours, A.",
  },
  source_confidence: 0.95,
};

function renderPage() {
  return render(
    <MemoryRouter>
      <Settings />
    </MemoryRouter>,
  );
}

describe("Settings", () => {
  beforeEach(() => {
    getSettings.mockReset();
    saveStyle.mockReset();
    clearStyle.mockReset();
    updateGeneration.mockReset();
    getSettings.mockReturnValue({
      data: { style: null, temperature: null, top_p: null },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
  });

  it("shows a loading state while fetching", () => {
    getSettings.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows an empty state when no style is set", () => {
    renderPage();
    expect(screen.getByText(/no writing style set yet/i)).toBeInTheDocument();
  });

  it("presents the saved style read-only", () => {
    getSettings.mockReturnValue({
      data: { style: profile, temperature: 0.8, top_p: 0.9 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByText("my-voice")).toBeInTheDocument();
    expect(screen.getByText("wry, long-form")).toBeInTheDocument();
    expect(screen.getByText("16 avg words / sentence")).toBeInTheDocument();
    expect(screen.getByText("95% confidence")).toBeInTheDocument();
    expect(screen.getByText("Hooks")).toBeInTheDocument();
    expect(screen.getByText("question")).toBeInTheDocument();
    expect(screen.getByText("rhetorical-question")).toBeInTheDocument();
    expect(screen.getByText("“Why? Why not?”")).toBeInTheDocument();
  });

  it("hides empty sections", () => {
    getSettings.mockReturnValue({
      data: { style: profile, temperature: 0.8, top_p: 0.9 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.queryByText("Story beats")).not.toBeInTheDocument();
    expect(screen.queryByText("Direct address")).not.toBeInTheDocument();
  });

  it("analyzes samples, saves, and presents the result", async () => {
    saveStyle.mockImplementation(() => ({
      unwrap: () => Promise.resolve({ style: profile }),
    }));
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByPlaceholderText(/Paste one or more/), "Sample body here.");
    await user.click(screen.getByRole("button", { name: "Analyze & save" }));

    expect(saveStyle).toHaveBeenCalledWith({
      samples: "Sample body here.",
    });
    expect(await screen.findByText("my-voice")).toBeInTheDocument();
  });

  it("hides the analyze form once a style is set", () => {
    getSettings.mockReturnValue({
      data: { style: profile, temperature: 0.8, top_p: 0.9 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByText("my-voice")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove style" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Analyze & save" })).not.toBeInTheDocument();
  });

  it("shows an error when analysis fails", async () => {
    saveStyle.mockImplementation(() => ({
      unwrap: () => Promise.reject(new Error("boom")),
    }));
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByPlaceholderText(/Paste one or more/), "Sample body here.");
    await user.click(screen.getByRole("button", { name: "Analyze & save" }));

    expect(
      await screen.findByText(/could not analyze your writing style/i),
    ).toBeInTheDocument();
  });

  it("removes the style", async () => {
    getSettings.mockReturnValue({
      data: { style: profile, temperature: 0.8, top_p: 0.9 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    clearStyle.mockImplementation(() => ({ unwrap: () => Promise.resolve() }));
    const user = userEvent.setup();
    const view = renderPage();

    await user.click(screen.getByRole("button", { name: "Remove style" }));

    expect(clearStyle).toHaveBeenCalled();
    getSettings.mockReturnValue({
      data: { style: null, temperature: null, top_p: null },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    view.rerender(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    );
    expect(screen.getByText(/no writing style set yet/i)).toBeInTheDocument();
  });

  it("disables the analyze button until samples are provided", () => {
    renderPage();
    expect(screen.getByRole("button", { name: "Analyze & save" })).toBeDisabled();
  });

  it("shows sampling defaults when unset", () => {
    renderPage();
    expect(screen.getByLabelText(/temperature/i)).toHaveValue(0.8);
    expect(screen.getByLabelText(/top-p/i)).toHaveValue(0.9);
  });

  it("shows stored sampling values", () => {
    getSettings.mockReturnValue({
      data: { style: null, temperature: 1.2, top_p: 0.6 },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByLabelText(/temperature/i)).toHaveValue(1.2);
    expect(screen.getByLabelText(/top-p/i)).toHaveValue(0.6);
  });

  it("saves generation settings", async () => {
    updateGeneration.mockImplementation(() => ({
      unwrap: () =>
        Promise.resolve({ style: null, temperature: 0.5, top_p: 0.8 }),
    }));
    const user = userEvent.setup();
    renderPage();

    const tempInput = screen.getByLabelText(/temperature/i);
    await user.clear(tempInput);
    await user.type(tempInput, "0.5");
    const topInput = screen.getByLabelText(/top-p/i);
    await user.clear(topInput);
    await user.type(topInput, "0.8");

    await user.click(screen.getByRole("button", { name: "Save generation settings" }));

    expect(updateGeneration).toHaveBeenCalledWith({ temperature: 0.5, top_p: 0.8 });
    expect(await screen.findByText("Generation settings saved.")).toBeInTheDocument();
  });

  it("shows an error when saving generation settings fails", async () => {
    updateGeneration.mockImplementation(() => ({
      unwrap: () => Promise.reject(new Error("boom")),
    }));
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole("button", { name: "Save generation settings" }));

    expect(
      await screen.findByText(/could not save generation settings/i),
    ).toBeInTheDocument();
  });
});