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
    }),
    mockLogin: build.mutation<User, MockLoginRequest>({
      query: (body) => ({ url: "/auth/mock", method: "POST", body }),
    }),
    logout: build.mutation<{ ok: boolean }, void>({
      query: () => ({ url: "/auth/logout", method: "POST" }),
    }),
  }),
});

export const {
  useGetMeQuery,
  useMockLoginMutation,
  useLogoutMutation,
} = authApi;
