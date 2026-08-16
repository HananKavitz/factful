import { describe, expect, it } from "vitest";
import type { User } from "../../types";
import reducer, { clearUser, setUser } from "./authSlice";

const alice: User = {
  id: 1,
  email: "alice@example.com",
  name: "Alice",
  picture: null,
};

describe("authSlice", () => {
  it("stores the user on setUser", () => {
    const state = reducer(undefined, setUser(alice));
    expect(state.user).toEqual(alice);
  });

  it("clears the user on clearUser", () => {
    const state = reducer({ user: alice }, clearUser());
    expect(state.user).toBeNull();
  });
});
