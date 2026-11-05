// The renderer of each view block kind (decision 16.1), as cardKinds.tsx is for cards: the AI chooses the blocks, and
// only these vetted components draw them. A kind with no renderer here shows nothing. Charts, ask and open come later.
import type { JSX } from "react";
import { Figures, Group, Heading, Prose, Table } from "./blocks";
import type { ViewBlock } from "./types";

type Renderers = { [K in ViewBlock["kind"]]: (p: { block: Extract<ViewBlock, { kind: K }> }) => JSX.Element };

export const viewBlocks: Renderers = {
  heading: Heading,
  prose: Prose,
  figures: Figures,
  table: Table,
  group: Group,
};
