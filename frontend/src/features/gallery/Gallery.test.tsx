import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { StorySummary } from "../../types";
import { Gallery } from "./Gallery";

const listStories = vi.hoisted(() => vi.fn());

vi.mock("../stories/storiesApi", () => ({
  useListStoriesQuery: (...args: unknown[]) => listStories(...args),
}));

const story: StorySummary = {
  id: 1,
  title: "Chip demand in 2026",
  prompt: "semiconductors",
  score: 84,
  created_at: "2026-01-15T10:00:00Z",
  updated_at: "2026-01-15T10:00:00Z",
};

function renderGallery() {
  return render(
    <MemoryRouter>
      <Gallery />
    </MemoryRouter>,
  );
}

describe("Gallery", () => {
  beforeEach(() => {
    listStories.mockReset();
  });

  it("shows a loading state while fetching", () => {
    listStories.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      refetch: vi.fn(),
    });
    renderGallery();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("lists stories as links to their editor", () => {
    listStories.mockReturnValue({
      data: [story],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderGallery();
    const link = screen.getByRole("link", { name: /Chip demand in 2026/ });
    expect(link).toHaveAttribute("href", "/stories/1");
    expect(screen.getByText(/score 84/)).toBeInTheDocument();
  });

  it("shows an empty state when there are no stories", () => {
    listStories.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderGallery();
    expect(
      screen.getByText("No stories yet. Create your first one."),
    ).toBeInTheDocument();
  });

  it("shows an error with a retry button when loading fails", async () => {
    const refetch = vi.fn();
    listStories.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch,
    });
    const user = userEvent.setup();
    renderGallery();

    expect(screen.getByText(/couldn't load your stories/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});