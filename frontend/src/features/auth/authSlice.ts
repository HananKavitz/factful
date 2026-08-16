import { createSlice } from "@reduxjs/toolkit";
import type { User } from "../../types";

interface AuthState {
  user: User | null;
}

const initialState: AuthState = { user: null };

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    setUser(state, action: { payload: User | null }) {
      state.user = action.payload;
    },
    clearUser(state) {
      state.user = null;
    },
  },
});

export const { setUser, clearUser } = authSlice.actions;
export default authSlice.reducer;
