// For tests only: Settings at one section, inside a router as the app places it.
import { createMemoryRouter, RouterProvider } from "react-router";
import { renderIn } from "@/design/test/harness";
import type { Dir } from "@/texts/types";
import { Settings } from "./Settings";

export function openSettings(dir: Dir, section: string) {
  const router = createMemoryRouter([{ path: "/settings/:section", element: <Settings /> }], { initialEntries: [`/settings/${section}`] });
  renderIn(dir, <RouterProvider router={router} />);
  return router;
}
