import { baseApi } from "../../app/api";
import type {
  JobStatus,
  StoryDetail,
  StorySummary,
} from "../../types";

export interface CreateStoryRequest {
  topic: string;
  angle?: string | null;
  instructions?: string | null;
}

export interface UpdateStoryRequest {
  title?: string;
  markdown?: string;
}

export interface EditStoryRequest {
  prompt: string;
}

type StoryTag = { type: "Story"; id: number | "LIST" };

export const storiesApi = baseApi.injectEndpoints({
  endpoints: (build) => ({
    listStories: build.query<StorySummary[], void>({
      query: () => ({ url: "/stories" }),
      providesTags: (result) =>
        result
          ? [
              ...result.map((story) => ({ type: "Story" as const, id: story.id })),
              { type: "Story" as const, id: "LIST" },
            ]
          : [{ type: "Story" as const, id: "LIST" }],
    }),
    createStory: build.mutation<JobStatus, CreateStoryRequest>({
      query: (body) => ({ url: "/stories", method: "POST", body }),
      invalidatesTags: [{ type: "Story", id: "LIST" }],
    }),
    getStory: build.query<StoryDetail, number>({
      query: (id) => ({ url: `/stories/${id}` }),
      providesTags: (_result, _error, id): StoryTag[] => [
        { type: "Story", id },
      ],
    }),
    updateStory: build.mutation<
      StoryDetail,
      { id: number; body: UpdateStoryRequest }
    >({
      query: ({ id, body }) => ({ url: `/stories/${id}`, method: "PUT", body }),
      invalidatesTags: (_result, _error, arg): StoryTag[] => [
        { type: "Story", id: arg.id },
      ],
    }),
    editStory: build.mutation<
      StoryDetail,
      { id: number; body: EditStoryRequest }
    >({
      query: ({ id, body }) => ({
        url: `/stories/${id}/edit`,
        method: "POST",
        body,
      }),
      invalidatesTags: (_result, _error, arg): StoryTag[] => [
        { type: "Story", id: arg.id },
      ],
    }),
  }),
});

export const {
  useListStoriesQuery,
  useCreateStoryMutation,
  useGetStoryQuery,
  useUpdateStoryMutation,
  useEditStoryMutation,
} = storiesApi;
