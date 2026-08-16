import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useDebouncedValue } from "./StoryEditor";

describe("useDebouncedValue", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("stays stale until the delay elapses", () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(
      ({ value }: { value: string }) => useDebouncedValue(value, 800),
      { initialProps: { value: "a" } },
    );

    expect(result.current).toBe("a");

    rerender({ value: "b" });
    expect(result.current).toBe("a");

    act(() => {
      vi.advanceTimersByTime(800);
    });
    expect(result.current).toBe("b");
  });
});
