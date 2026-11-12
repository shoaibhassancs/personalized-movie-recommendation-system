import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { clearServed } from "../served";

afterEach(() => {
  cleanup();
  clearServed();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});
