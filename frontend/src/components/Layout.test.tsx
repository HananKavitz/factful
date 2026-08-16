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
  it("makes the factful brand a link to the gallery with no nav links", () => {
    renderLayout(alice);

    const sidebar = screen.getByRole("complementary");
    const brand = within(sidebar).getByRole("link", { name: "factful" });
    expect(brand).toHaveAttribute("href", "/");
    expect(within(sidebar).queryByRole("link", { name: "Stories" })).not.toBeInTheDocument();
    expect(within(sidebar).queryByRole("navigation")).not.toBeInTheDocument();
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