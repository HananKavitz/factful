import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { NoteModal } from "./NoteModal";

function renderModal(props: Partial<Parameters<typeof NoteModal>[0]> = {}) {
  return render(
    <NoteModal
      instructions=""
      generatedNote={null}
      onInstructionsChange={() => {}}
      onGenerate={() => {}}
      onClose={() => {}}
      onCopy={() => {}}
      onNoteChange={() => {}}
      loading={false}
      error={null}
      {...props}
    />,
  );
}

describe("NoteModal", () => {
  it("lets the user inject instructions before generating", () => {
    const onInstructionsChange = vi.fn();
    renderModal({ onInstructionsChange });

    const textarea = screen.getByLabelText("Instructions (optional)") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "Keep it under 20 words." } });
    expect(onInstructionsChange).toHaveBeenCalledWith("Keep it under 20 words.");
  });

  it("triggers generation when Generate note is clicked", () => {
    const onGenerate = vi.fn();
    renderModal({ onGenerate });

    fireEvent.click(screen.getByRole("button", { name: "Generate note" }));
    expect(onGenerate).toHaveBeenCalled();
  });

  it("shows a loading state while generating", () => {
    renderModal({ loading: true });

    expect(screen.getByText("Generating note…")).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("shows an error state", () => {
    renderModal({ error: "Generation failed. Please try again." });

    expect(screen.getByText("Generation failed. Please try again.")).toBeInTheDocument();
  });

  it("calls onCopy with the current note when Copy is clicked", () => {
    const onCopy = vi.fn();
    renderModal({ generatedNote: "Check out my latest article!", onCopy });

    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    expect(onCopy).toHaveBeenCalledWith("Check out my latest article!");
  });

  it("calls onNoteChange when the user edits the note textarea", () => {
    const onNoteChange = vi.fn();
    renderModal({ generatedNote: "Check out my latest article!", onNoteChange });

    const textarea = screen.getByRole("textbox");
    fireEvent.change(textarea, { target: { value: "Edited note text!" } });
    expect(onNoteChange).toHaveBeenCalledWith("Edited note text!");
  });

  it("calls onClose when Close is clicked", () => {
    const onClose = vi.fn();
    renderModal({ generatedNote: "Some note", onClose });

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("renders the heading with Substack Note title", () => {
    renderModal();
    expect(screen.getByText("Substack Note")).toBeInTheDocument();
  });
});