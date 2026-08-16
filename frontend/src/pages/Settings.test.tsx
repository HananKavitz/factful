import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StyleProfile } from "../types";
import { Settings } from "./Settings";

const getSettings = vi.hoisted(() => vi.fn());
const saveStyle = vi.hoisted(() => vi.fn());
const clearStyle = vi.hoisted(() => vi.fn());

vi.mock("../features/settings/settingsApi", () => ({
  useGetSettingsQuery: () => getSettings(),
  useSaveStyleMutation: () => [saveStyle, { isLoading: false }],
  useClearStyleMutation: () => [clearStyle, { isLoading: false }],
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
    getSettings.mockReturnValue({
      data: { style: null },
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
      data: { style: profile },
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
      data: { style: profile },
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

    await user.type(screen.getByPlaceholderText("e.g. My newsletter voice"), "my-voice");
    await user.type(screen.getByPlaceholderText(/Paste one or more/), "Sample body here.");
    await user.click(screen.getByRole("button", { name: "Analyze & save" }));

    expect(saveStyle).toHaveBeenCalledWith({
      name: "my-voice",
      samples: "Sample body here.",
    });
    expect(await screen.findByText("my-voice")).toBeInTheDocument();
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
      data: { style: profile },
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
      data: { style: null },
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
});