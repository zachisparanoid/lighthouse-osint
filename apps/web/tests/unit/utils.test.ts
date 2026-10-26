import { describe, expect, it } from "vitest";

import { confidenceColor, relativeTime, truncate } from "@/lib/utils";

describe("confidenceColor", () => {
  it("bands the score by color", () => {
    expect(confidenceColor(90)).toBe("var(--success)");
    expect(confidenceColor(75)).toBe("var(--success)");
    expect(confidenceColor(60)).toBe("var(--accent)");
    expect(confidenceColor(30)).toBe("var(--warning)");
    expect(confidenceColor(10)).toBe("var(--danger)");
  });
});

describe("truncate", () => {
  it("leaves short strings", () => {
    expect(truncate("abc", 10)).toBe("abc");
  });
  it("ellipsizes long strings", () => {
    expect(truncate("abcdefghij", 5)).toBe("abcd…");
  });
});

describe("relativeTime", () => {
  it("handles null", () => {
    expect(relativeTime(null)).toBe("—");
  });
  it("formats hours ago", () => {
    const twoHoursAgo = new Date(Date.now() - 2 * 3600 * 1000).toISOString();
    expect(relativeTime(twoHoursAgo)).toBe("2h ago");
  });
  it("formats minutes ago", () => {
    const tenMinAgo = new Date(Date.now() - 10 * 60 * 1000).toISOString();
    expect(relativeTime(tenMinAgo)).toBe("10m ago");
  });
});
