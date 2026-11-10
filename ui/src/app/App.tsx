// The new interface: hash routes (the installed app is served from one file), the gate, the frame and the places.
import { createHashRouter, RouterProvider } from "react-router";
import { appRoutes } from "./routes";

const router = createHashRouter(appRoutes);

export function App() {
  return <RouterProvider router={router} />;
}
