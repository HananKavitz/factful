import { baseApi } from "../../app/api";
import type { JobStatus } from "../../types";

export const jobsApi = baseApi.injectEndpoints({
  endpoints: (build) => ({
    getJob: build.query<JobStatus, string>({
      query: (jobId) => ({ url: `/jobs/${jobId}` }),
    }),
    cancelJob: build.mutation<JobStatus, string>({
      query: (jobId) => ({ url: `/jobs/${jobId}/cancel`, method: "POST" }),
    }),
  }),
});

export const { useGetJobQuery, useCancelJobMutation } = jobsApi;
