import { configureStore } from "@reduxjs/toolkit";
import { render, screen, within } from "@testing-library/react";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { User } from "../types";
import authReducer from "../features/auth/authSlice";
import { Layout } from "./Layout";

vi.mock("../features/auth/authApi", () => ({
  useLogoutMutation: () => [
    vi.fn(() => ({ unwrap: () => Promise.resolve({ ok: true }) })),
    { isLoading: false },
  ],
}));

const alice: User = {
  id: 1,
  email: "alice@example.com",
  name: "Alice",
  picture: null,
};

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
  it("renders the brand and Stories in the sidebar navigation", () => {
    renderLayout(alice);

    const sidebar = screen.getByRole("complementary");
    expect(within(sidebar).getByText("factful")).toBeInTheDocument();
    const nav = within(sidebar).getByRole("navigation");
    expect(within(nav).getByRole("link", { name: "Stories" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "Settings" })).not.toBeInTheDocument();
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