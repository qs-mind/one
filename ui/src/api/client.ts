// The typed way to call the Phase 1 routes: client.GET("/home"), client.POST("/projects/{project_id}/room", …).
// The routes and their shapes come from contract.ts, which `npm run contract` writes from the core's own models.
// Every call still leaves through api() (../api.ts), the one way the screen reaches the core.
//
// A call answers { data } on 2xx and { error } on a refusal (`error.error` is the core's {en, ar} words). It throws
// only when the core cannot be reached or the call is stopped, as api() does.
import createClient from "openapi-fetch";
import { api } from "../api";
import type { components, paths } from "./contract";

/** The contract's shapes by name: Schemas["Home"], Schemas["Finding"]… */
export type Schemas = components["schemas"];

/** A source as the kept viewers take it (ui/src/sources). The contract's `Source` mirrors this shape. */
export type { Source } from "../deliverables/types";

/** The contract's live events of one tender, and those that belong to none. They arrive on the activity stream:
 * subscribeTender and subscribeGeneral in ../activity.ts. */
export type TenderActivity =
  | Schemas["PlanEvent"]
  | Schemas["FindingEvent"]
  | Schemas["RoomEvent"]
  | Schemas["MemberEvent"]
  | Schemas["TenderEvent"]
  | Schemas["BriefEvent"];
export type GeneralActivity = Schemas["HomeEvent"] | Schemas["SettingEvent"] | Schemas["SetupEvent"] | Schemas["LessonsEvent"];

export const client = createClient<paths>({
  // openapi-fetch builds a Request, which needs a whole address. Only the path after it is handed to api().
  baseUrl: "http://core.invalid",
  fetch: async (request: Request) => {
    const url = new URL(request.url);
    // A body travels as text: the installed app's shell carries no stream.
    const body = request.body === null ? undefined : await request.text();
    return api(url.pathname + url.search, { method: request.method, headers: request.headers, body, signal: request.signal });
  },
});
