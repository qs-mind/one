// The new interface: hash routes (the installed app is served from one file), the gate, the frame and the places, and
// the zoom keys (Ctrl/Cmd with = - 0) on every one of them.
import { createHashRouter, RouterProvider } from "react-router";
import { useZoomKeys } from "../ui/scale";
import { appRoutes } from "./routes";

const router = createHashRouter(appRoutes);

export function App() {
  useZoomKeys();
  return <RouterProvider router={router} />;
}
