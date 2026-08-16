import { baseApi } from "../../app/api";
import type { JobStatus } from "../../types";

export const jobsApi = baseApi.injectEndpoints({
  endpoints: (build) => ({
    getJob: build.query<JobStatus, string>({
      query: (jobId) => ({ url: `/jobs/${jobId}` }),
    }),
  }),
});

export const { useGetJobQuery } = jobsApi;
