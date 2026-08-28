import { configureStore } from "@reduxjs/toolkit";
import { render, screen, within } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { StorySummary, User } from "../types";
import authReducer from "../features/auth/authSlice";
import { Layout } from "./Layout";

vi.mock("../features/auth/authApi", () => ({
  useLogoutMutation: () => [
    vi.fn(() => ({ unwrap: () => Promise.resolve({ ok: true }) })),
    { isLoading: false },
  ],
}));

const listStories = vi.hoisted(() => vi.fn());

vi.mock("../features/stories/storiesApi", () => ({
  useListStoriesQuery: (...args: unknown[]) => listStories(...args),
}));

const alice: User = {
  id: 1,
  email: "alice@example.com",
  name: "Alice",
  picture: null,
};

const stories: StorySummary[] = [
  {
    id: 1,
    title: "Chip demand in 2026",
    prompt: "semiconductors",
    score: 84,
    created_at: "2026-01-15T10:00:00Z",
    updated_at: "2026-01-15T10:00:00Z",
  },
  {
    id: 2,
    title: "Solar cells",
    prompt: "renewables",
    score: null,
    created_at: "2026-02-01T10:00:00Z",
    updated_at: "2026-02-01T10:00:00Z",
  },
];

function renderLayout(user: User | null) {
  const store = configureStore({
    reducer: { auth: authReducer },
    preloadedState: { auth: { user } },
  });
  return render(
    <Provider store={store}>
      <MemoryRouter>
        <Layout>page content</Layout>
      </MemoryRouter>
    </Provider>,
  );
}

describe("Layout", () => {
  beforeEach(() => {
    listStories.mockReset();
    listStories.mockReturnValue({
      data: stories,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
  });

  it("makes the factful brand a header link to the gallery with no nav links", () => {
    renderLayout(alice);

    const header = screen.getByRole("banner");
    const brand = within(header).getByRole("link", { name: "factful" });
    expect(brand).toHaveAttribute("href", "/");
    const sidebar = screen.getByRole("complementary");
    expect(within(sidebar).queryByRole("link", { name: "Stories" })).not.toBeInTheDocument();
    expect(within(sidebar).queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("lists the user's stories in the sidebar as links", () => {
    renderLayout(alice);

    const sidebar = screen.getByRole("complementary");
    expect(
      within(sidebar).getByRole("link", { name: "Chip demand in 2026" }),
    ).toHaveAttribute("href", "/stories/1");
    expect(
      within(sidebar).getByRole("link", { name: "Solar cells" }),
    ).toHaveAttribute("href", "/stories/2");
  });

  it("shows no story list when there are no stories", () => {
    listStories.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderLayout(alice);

    const sidebar = screen.getByRole("complementary");
    expect(
      within(sidebar).queryByRole("link", { name: "Chip demand in 2026" }),
    ).not.toBeInTheDocument();
  });

  it("places a settings gear icon in the lower part of the sidebar", () => {
    renderLayout(alice);

    const sidebar = screen.getByRole("complementary");
    const footer = within(sidebar).getByRole("contentinfo");
    expect(within(footer).getByRole("link", { name: "Settings" })).toBeInTheDocument();
  });

  it("shows the user and a logout action in the lower part of the sidebar", () => {
    renderLayout(alice);

    const footer = screen.getByRole("contentinfo");
    expect(within(footer).getByText("Alice")).toBeInTheDocument();
    expect(within(footer).getByRole("button", { name: "Log out" })).toBeInTheDocument();
  });

  it("renders children in the main area", () => {
    renderLayout(alice);
    expect(screen.getByText("page content")).toBeInTheDocument();
  });
});