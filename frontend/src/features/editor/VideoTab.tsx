import type { VideoInfo } from "../../types";

const STAGE_LABELS: Record<string, string> = {
  preparing: "Preparing assets…",
  fetching_media: "Downloading images & generating audio…",
  composing: "Building slides…",
  encoding: "Encoding video (this takes the longest)…",
  finalizing: "Finalizing…",
};

function stageDisplayName(stage: string | null): string {
  if (!stage) return "Rendering…";
  return STAGE_LABELS[stage] ?? stage;
}

function ProgressBar({ value, stage }: { value: number | null; stage: string | null }) {
  const pct = value ?? 0;
  return (
    <div className="w-full">
      <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
        <span>{stageDisplayName(stage)}</span>
        <span>{pct}%</span>
      </div>
      <div
        className="h-2 w-full overflow-hidden rounded-full bg-slate-200"
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className="h-full rounded-full bg-cyan-600 transition-all duration-500 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

interface VideoTabProps {
  voice: string;
  onVoiceChange: (voice: string) => void;
  playableVideos: VideoInfo[];
  selectedVideo: VideoInfo | null;
  selectedVideoId: number | null;
  onSelectedVideoIdChange: (id: number) => void;
  hasPlayable: boolean;
  videos: VideoInfo[];
  isRendering: boolean;
  onRenderVideo: () => void;
  onCancelVideo: () => void;
  isCancelling: boolean;
  videoError: string | null;
  videoProgress: number | null;
  videoStage: string | null;
}

const TTS_VOICES = [
  { value: "en-US-AriaNeural", label: "Aria (US, Female)" },
  { value: "en-US-GuyNeural", label: "Guy (US, Male)" },
  { value: "en-US-JennyNeural", label: "Jenny (US, Female)" },
  { value: "en-US-MichelleNeural", label: "Michelle (US, Female)" },
  { value: "en-GB-SoniaNeural", label: "Sonia (UK, Female)" },
  { value: "en-GB-RyanNeural", label: "Ryan (UK, Male)" },
  { value: "en-AU-NatashaNeural", label: "Natasha (AU, Female)" },
  { value: "en-AU-WilliamNeural", label: "William (AU, Male)" },
];

export function VideoTab({
  voice,
  onVoiceChange,
  playableVideos,
  selectedVideo,
  onSelectedVideoIdChange,
  hasPlayable,
  videos,
  isRendering,
  onRenderVideo,
  onCancelVideo,
  isCancelling,
  videoError,
  videoProgress,
  videoStage,
}: VideoTabProps) {
  return (
    <div className="space-y-4">
      {/* Video player when playable videos exist */}
      {hasPlayable && selectedVideo && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-medium text-slate-700">Video</h3>
            <div className="flex items-center gap-2">
              {playableVideos.length > 1 && (
                <select
                  value={selectedVideo.id}
                  onChange={(e) => onSelectedVideoIdChange(Number(e.target.value))}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs"
                >
                  {playableVideos.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.voice} — {new Date(v.created_at).toLocaleDateString()}
                    </option>
                  ))}
                </select>
              )}
              <select
                value={voice}
                onChange={(e) => onVoiceChange(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1 text-xs"
              >
                {TTS_VOICES.map((v) => (
                  <option key={v.value} value={v.value}>{v.label}</option>
                ))}
              </select>
              <button
                onClick={onRenderVideo}
                disabled={isRendering}
                className="text-xs text-cyan-600 hover:text-cyan-800 disabled:opacity-50"
              >
                {isRendering ? "Rendering…" : "Render new version"}
              </button>
            </div>
          </div>
          {isRendering && videoProgress != null && (
            <div className="mb-2">
              <ProgressBar
                value={videoProgress}
                stage={videoStage}
              />
              <button
                onClick={onCancelVideo}
                disabled={isCancelling}
                className="mt-1 text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
              >
                {isCancelling ? "Cancelling…" : "Cancel"}
              </button>
            </div>
          )}
          <video
            key={selectedVideo.id}
            controls
            className="w-full max-h-[calc(100vh-20rem)] rounded-md border"
            src={selectedVideo.url}
          >
            Your browser does not support the video tag.
          </video>
          <div className="mt-1 flex gap-4 text-xs text-slate-400">
            {selectedVideo.duration_seconds && (
              <span>{Math.round(selectedVideo.duration_seconds)}s</span>
            )}
            {selectedVideo.resolution && <span>{selectedVideo.resolution}</span>}
            {selectedVideo.file_size_bytes && (
              <span>{(selectedVideo.file_size_bytes / 1024 / 1024).toFixed(1)} MB</span>
            )}
          </div>
        </div>
      )}

      {/* Failed / missing videos list */}
      {videos && videos.length > 0 && !hasPlayable && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-2 text-sm font-medium text-slate-700">Videos</h3>
          <ul className="space-y-1">
            {videos.map((v) => (
              <li key={v.id} className="flex items-center gap-2 text-xs">
                <span className={v.file_exists ? "text-slate-700" : "text-red-500 line-through"}>
                  {v.voice} — {new Date(v.created_at).toLocaleDateString()}
                </span>
                {v.status === "failed" && (
                  <span className="text-red-500">
                    {v.error_message ? `(${v.error_message})` : "(failed)"}
                  </span>
                )}
                {!v.file_exists && <span className="text-red-500">(file missing)</span>}
              </li>
            ))}
          </ul>
          {!isRendering && (
            <div className="mt-2 flex items-center gap-2">
              <select
                value={voice}
                onChange={(e) => onVoiceChange(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1 text-xs"
              >
                {TTS_VOICES.map((v) => (
                  <option key={v.value} value={v.value}>{v.label}</option>
                ))}
              </select>
              <button
                onClick={onRenderVideo}
                className="rounded-md bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700"
              >
                Render Video
              </button>
            </div>
          )}
          {isRendering && (
            <div className="mt-2">
              <ProgressBar
                value={videoProgress}
                stage={videoStage}
              />
              <button
                onClick={onCancelVideo}
                disabled={isCancelling}
                className="mt-1 text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
              >
                {isCancelling ? "Cancelling…" : "Cancel"}
              </button>
            </div>
          )}
        </div>
      )}

      {/* No videos at all — show render controls directly */}
      {(!videos || videos.length === 0) && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="mb-2 text-sm font-medium text-slate-700">Video Generation</h3>
          {!isRendering && (
            <div className="flex items-center gap-2">
              <select
                value={voice}
                onChange={(e) => onVoiceChange(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1 text-xs"
              >
                {TTS_VOICES.map((v) => (
                  <option key={v.value} value={v.value}>{v.label}</option>
                ))}
              </select>
              <button
                onClick={onRenderVideo}
                className="rounded-md bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700"
              >
                Render Video
              </button>
            </div>
          )}
          {isRendering && (
            <div className="mt-2">
              <ProgressBar
                value={videoProgress}
                stage={videoStage}
              />
              <button
                onClick={onCancelVideo}
                disabled={isCancelling}
                className="mt-1 text-xs text-red-500 hover:text-red-700 disabled:opacity-50"
              >
                {isCancelling ? "Cancelling…" : "Cancel"}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Error banner */}
      {videoError && (
        <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
          {videoError}
        </div>
      )}
    </div>
  );
}
