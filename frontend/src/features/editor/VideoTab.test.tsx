import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { VideoTab } from "./VideoTab";
import type { VideoInfo } from "../../types";

const playableVideo: VideoInfo = {
  id: 1,
  url: "https://example.com/video.mp4",
  voice: "en-US-AriaNeural",
  duration_seconds: 120,
  file_size_bytes: 5_000_000,
  resolution: "1920x1080",
  status: "completed",
  error_message: null,
  file_exists: true,
  created_at: "2026-01-01T00:00:00Z",
};

const failedVideo: VideoInfo = {
  id: 2,
  url: "",
  voice: "en-US-GuyNeural",
  duration_seconds: null,
  file_size_bytes: null,
  resolution: null,
  status: "failed",
  error_message: "Processing error",
  file_exists: false,
  created_at: "2026-01-02T00:00:00Z",
};

const missingVideo: VideoInfo = {
  id: 3,
  url: "",
  voice: "en-US-JennyNeural",
  duration_seconds: null,
  file_size_bytes: null,
  resolution: null,
  status: "completed",
  error_message: null,
  file_exists: false,
  created_at: "2026-01-03T00:00:00Z",
};

const defaultProps = {
  voice: "en-US-AriaNeural",
  onVoiceChange: vi.fn(),
  playableVideos: [] as VideoInfo[],
  selectedVideo: null as VideoInfo | null,
  selectedVideoId: null as number | null,
  onSelectedVideoIdChange: vi.fn(),
  hasPlayable: false,
  videos: [] as VideoInfo[],
  isRendering: false,
  onRenderVideo: vi.fn(),
  videoError: null as string | null,
};

describe("VideoTab", () => {
  it("shows voice selector and render button when there are no videos", () => {
    render(<VideoTab {...defaultProps} />);

    expect(screen.getByText("Video Generation")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Render Video" }),
    ).toBeInTheDocument();
  });

  it("shows a spinner when rendering with no videos yet", () => {
    render(<VideoTab {...defaultProps} isRendering={true} />);

    expect(screen.getByText("Rendering…")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Render Video" }),
    ).not.toBeInTheDocument();
  });

  it("shows the video player when playable videos exist", () => {
    render(
      <VideoTab
        {...defaultProps}
        playableVideos={[playableVideo]}
        selectedVideo={playableVideo}
        selectedVideoId={playableVideo.id}
        hasPlayable={true}
        videos={[playableVideo]}
      />,
    );

    expect(screen.getByRole("heading", { name: "Video" })).toBeInTheDocument();
    expect(screen.getByText("Render new version")).toBeInTheDocument();
    const videoElement = document.querySelector("video");
    expect(videoElement).not.toBeNull();
    expect(videoElement!.getAttribute("src")).toBe(playableVideo.url);
  });

  it("shows video metadata for a playable video", () => {
    render(
      <VideoTab
        {...defaultProps}
        playableVideos={[playableVideo]}
        selectedVideo={playableVideo}
        selectedVideoId={playableVideo.id}
        hasPlayable={true}
        videos={[playableVideo]}
      />,
    );

    expect(screen.getByText("120s")).toBeInTheDocument();
    expect(screen.getByText("1920x1080")).toBeInTheDocument();
    expect(screen.getByText("4.8 MB")).toBeInTheDocument();
  });

  it("shows a dropdown to select between multiple playable videos", () => {
    const v2: VideoInfo = {
      ...playableVideo,
      id: 2,
      voice: "en-US-GuyNeural",
      created_at: "2026-02-01T00:00:00Z",
    };
    render(
      <VideoTab
        {...defaultProps}
        playableVideos={[playableVideo, v2]}
        selectedVideo={playableVideo}
        selectedVideoId={playableVideo.id}
        hasPlayable={true}
        videos={[playableVideo, v2]}
      />,
    );

    // There should be two <select> elements: one for video selection, one for voice
    const selects = screen.getAllByRole("combobox");
    expect(selects.length).toBeGreaterThanOrEqual(2);
  });

  it("shows failed videos list when only failed/missing videos exist", () => {
    render(
      <VideoTab
        {...defaultProps}
        videos={[failedVideo, missingVideo]}
      />,
    );

    expect(screen.getByText("Videos")).toBeInTheDocument();
    expect(screen.getByText(/Processing error/)).toBeInTheDocument();
    expect(screen.getAllByText(/file missing/).length).toBe(2);
    expect(
      screen.getByRole("button", { name: "Render Video" }),
    ).toBeInTheDocument();
  });

  it("does not show the player section when no playable videos exist", () => {
    render(
      <VideoTab
        {...defaultProps}
        videos={[failedVideo]}
      />,
    );

    expect(screen.queryByRole("video")).not.toBeInTheDocument();
    expect(screen.queryByText("Render new version")).not.toBeInTheDocument();
  });

  it("shows a rendering spinner alongside failed videos", () => {
    render(
      <VideoTab
        {...defaultProps}
        videos={[failedVideo]}
        isRendering={true}
      />,
    );

    expect(screen.getByText("Rendering…")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Render Video" }),
    ).not.toBeInTheDocument();
  });

  it("displays an error banner when videoError is set", () => {
    render(
      <VideoTab {...defaultProps} videoError="Something went wrong." />,
    );

    expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
  });

  it("calls onRenderVideo when the render button is clicked", async () => {
    const onRenderVideo = vi.fn();
    const user = userEvent.setup();

    render(
      <VideoTab
        {...defaultProps}
        onRenderVideo={onRenderVideo}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Render Video" }));
    expect(onRenderVideo).toHaveBeenCalledOnce();
  });

  it("calls onVoiceChange when a new voice is selected", async () => {
    const onVoiceChange = vi.fn();
    const user = userEvent.setup();

    render(
      <VideoTab
        {...defaultProps}
        onVoiceChange={onVoiceChange}
      />,
    );

    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "en-US-GuyNeural");
    expect(onVoiceChange).toHaveBeenCalledWith("en-US-GuyNeural");
  });
});
