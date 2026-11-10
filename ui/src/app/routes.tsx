// The new interface's routes, after the hash (#/tender/<id>/room). The gate stands before every place; the frame
// (rail and place) holds all but first launch.
import { Navigate, type RouteObject } from "react-router";
import { Welcome } from "@/firstlaunch2/Welcome";
import { Home } from "@/home/Home";
import { Settings } from "@/settings2/Settings";
import { Tender } from "@/tender/Tender";
import { Frame } from "./Frame";
import { FirstLaunchGate } from "./gates";
import { paths, WELCOME_STEPS } from "./paths";

export const appRoutes: RouteObject[] = [
  {
    element: <FirstLaunchGate />,
    children: [
      { path: "welcome", element: <Navigate to={paths.welcome(WELCOME_STEPS[0])} replace /> },
      { path: "welcome/:step", element: <Welcome /> },
      {
        element: <Frame />,
        children: [
          { index: true, element: <Home /> },
          { path: "tender/:id", element: <Tender /> },
          { path: "tender/:id/doc/:docId", element: <Tender /> },
          { path: "tender/:id/room", element: <Tender /> },
          { path: "tender/:id/member/:memberId", element: <Tender /> },
          { path: "settings", element: <Navigate to={paths.settings()} replace /> },
          { path: "settings/:section", element: <Settings /> },
        ],
      },
      { path: "*", element: <Navigate to={paths.home} replace /> },
    ],
  },
];
