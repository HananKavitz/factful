import { baseApi } from "../../app/api";
import type { Settings } from "../../types";

export interface SaveStyleRequest {
  name: string;
  samples: string;
}

export const settingsApi = baseApi.injectEndpoints({
  endpoints: (build) => ({
    getSettings: build.query<Settings, void>({
      query: () => ({ url: "/settings" }),
      providesTags: () => [{ type: "Settings", id: "STYLE" }],
    }),
    saveStyle: build.mutation<Settings, SaveStyleRequest>({
      query: (body) => ({ url: "/settings/style", method: "POST", body }),
      invalidatesTags: [{ type: "Settings", id: "STYLE" }],
    }),
    clearStyle: build.mutation<void, void>({
      query: () => ({ url: "/settings/style", method: "DELETE" }),
      invalidatesTags: [{ type: "Settings", id: "STYLE" }],
    }),
  }),
});

export const {
  useGetSettingsQuery,
  useSaveStyleMutation,
  useClearStyleMutation,
} = settingsApi;