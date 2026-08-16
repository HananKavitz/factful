import { render, screen } from "@testing-library/react";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "../../types";
import authReducer from "./authSlice";

const getMeMock = vi.fn();

vi.mock("./authApi", () => ({
  useGetMeQuery: () => getMeMock(),
  useMockLoginMutation: () => [vi.fn(), { isLoading: false }],
}));

import { AuthGate } from "./AuthGate";

const alice: User = {
  id: 1,
  email: "alice@example.com",
  name: "Alice",
  picture: null,
};

function renderAuthGate(overrides: Record<string, unknown>) {
  getMeMock.mockReturnValue(overrides);
  const store = configureStore({ reducer: { auth: authReducer } });
  return render(
    <Provider store={store}>
      <AuthGate>protected content</AuthGate>
    </Provider>,
  );
}

describe("AuthGate", () => {
  beforeEach(() => {
    getMeMock.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders children when signed in", () => {
    renderAuthGate({
      data: alice,
      refetch: vi.fn(),
      isUninitialized: false,
      isFetching: false,
      isSuccess: true,
      isError: false,
    });
    expect(screen.getByText("protected content")).toBeInTheDocument();
  });

  it("shows a loading state while checking auth", () => {
    renderAuthGate({
      data: undefined,
      refetch: vi.fn(),
      isUninitialized: true,
      isFetching: false,
      isSuccess: false,
      isError: false,
    });
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows the sign-in screen when unauthenticated", () => {
    renderAuthGate({
      data: undefined,
      refetch: vi.fn(),
      isUninitialized: false,
      isFetching: false,
      isSuccess: false,
      isError: true,
    });
    expect(
      screen.getByRole("link", { name: "Sign in with Google" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("protected content")).not.toBeInTheDocument();
  });
});
