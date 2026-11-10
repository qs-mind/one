// First launch inside the router: U7's three steps. When they end, Home; leaving /welcome makes the gate ask the
// core again (gates.tsx). The step in the address is the gate's; the screen also works out its own step from the
// core, so the two agree until U9 keeps only one.
import { useNavigate, useParams } from "react-router";
import { Welcome } from "@/firstlaunch2/Welcome";
import { paths } from "./paths";

export function WelcomeRoute() {
  const { step } = useParams();
  const navigate = useNavigate();
  return (
    <div data-place="welcome" data-step={step}>
      <Welcome onDone={() => navigate(paths.home, { replace: true })} />
    </div>
  );
}
