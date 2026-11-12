import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { StarRating } from "../components/StarRating";
import { GENRES } from "../constants";

describe("StarRating", () => {
  it("reports the chosen half-star value and clears", async () => {
    const onChange = vi.fn();
    const onClear = vi.fn();
    render(<StarRating value={3.5} onChange={onChange} onClear={onClear} />);
    expect(screen.getByRole("button", { name: "3.5 stars" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await userEvent.click(screen.getByRole("button", { name: "0.5 stars" }));
    expect(onChange).toHaveBeenCalledWith(0.5);
    await userEvent.click(screen.getByRole("button", { name: "Clear rating" }));
    expect(onClear).toHaveBeenCalled();
  });

  it("offers exactly ten values from 0.5 to 5 and disables clear when unrated", () => {
    render(<StarRating value={null} onChange={vi.fn()} onClear={vi.fn()} />);
    expect(screen.getAllByRole("button", { name: /star/ })).toHaveLength(10);
    expect(screen.getByText("Not rated")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear rating" })).toBeDisabled();
  });
});

describe("genre constant", () => {
  it("has the 19 MovieLens genres, sorted, without the no-genre marker", () => {
    expect(GENRES).toHaveLength(19);
    expect([...GENRES].sort()).toEqual([...GENRES]);
    expect(GENRES.join()).not.toMatch(/no genres/i);
  });
});
