import { configureStore } from "@reduxjs/toolkit";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { baseApi } from "../../app/api";
import type { User } from "../../types";
import { Layout } from "../../components/Layout";
import { AuthGate } from "./AuthGate";
import authReducer from "./authSlice";

const alice: User = {
  id: 1,
  email: "alice@example.com",
  name: "Alice",
  picture: null,
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function makeStore(initialUser: User | null) {
  return configureStore({
    reducer: {
      auth: authReducer,
      [baseApi.reducerPath]: baseApi.reducer,
    },
    middleware: (getDefaultMiddleware) =>
      getDefaultMiddleware().concat(baseApi.middleware),
    preloadedState: { auth: { user: initialUser } },
  });
}

describe("logout flow", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });

  it("clears the user and returns to the sign-in screen", async () => {
    let authed = true;
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const method = init?.method ?? "GET";
        if (url.endsWith("/api/auth/me")) {
          return authed
            ? jsonResponse(200, alice)
            : jsonResponse(401, { detail: "unauthenticated" });
        }
        if (url.endsWith("/api/auth/logout") && method === "POST") {
          authed = false;
          return jsonResponse(200, { ok: true });
        }
        return jsonResponse(404, { detail: "not found" });
      }),
    );

    const store = makeStore(alice);
    const user = userEvent.setup();

    render(
      <Provider store={store}>
        <MemoryRouter initialEntries={["/"]}>
          <AuthGate>
            <Layout>dashboard content</Layout>
          </AuthGate>
        </MemoryRouter>
      </Provider>,
    );

    expect(screen.getByText("dashboard content")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Log out" }));

    expect(
      await screen.findByRole("link", { name: "Sign in with Google" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("dashboard content")).not.toBeInTheDocument();
    expect(store.getState().auth.user).toBeNull();
  });
});
