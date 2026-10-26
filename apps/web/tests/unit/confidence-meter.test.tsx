import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConfidenceMeter } from "@/components/entity/ConfidenceMeter";

describe("ConfidenceMeter", () => {
  it("renders the numeric value", () => {
    render(<ConfidenceMeter value={82} />);
    expect(screen.getByText("82")).toBeInTheDocument();
  });

  it("hides the label when showLabel is false", () => {
    render(<ConfidenceMeter value={50} showLabel={false} />);
    expect(screen.queryByText("50")).not.toBeInTheDocument();
  });

  it("colors the value by confidence band", () => {
    render(<ConfidenceMeter value={90} />);
    const label = screen.getByText("90");
    expect(label).toHaveStyle({ color: "var(--success)" });
  });
});
