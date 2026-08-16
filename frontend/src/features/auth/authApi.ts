import { baseApi } from "../../app/api";
import type { User } from "../../types";

export interface MockLoginRequest {
  email: string;
  name?: string;
}

export const authApi = baseApi.injectEndpoints({
  endpoints: (build) => ({
    getMe: build.query<User, void>({
      query: () => ({ url: "/auth/me" }),
      providesTags: () => [{ type: "Auth", id: "ME" }],
    }),
    mockLogin: build.mutation<User, MockLoginRequest>({
      query: (body) => ({ url: "/auth/mock", method: "POST", body }),
      invalidatesTags: [{ type: "Auth", id: "ME" }],
    }),
    logout: build.mutation<{ ok: boolean }, void>({
      query: () => ({ url: "/auth/logout", method: "POST" }),
      invalidatesTags: [{ type: "Auth", id: "ME" }],
    }),
  }),
});

export const {
  useGetMeQuery,
  useMockLoginMutation,
  useLogoutMutation,
} = authApi;
