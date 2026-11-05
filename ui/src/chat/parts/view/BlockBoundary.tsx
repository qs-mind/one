// Each block of a view in its own error boundary: a block that throws costs only itself (a quiet line in its place),
// and the rest of the view still shows. A block of a kind this app does not know (from a newer core) shows nothing.
import { Component, type JSX, type ReactNode } from "react";
import { t } from "../../../i18n";

export type BlockRegistry = Partial<Record<string, (p: { block: never }) => JSX.Element>>;

class Boundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) return <p className="text-slate">{t("viewBlockFailed")}</p>;
    return this.props.children;
  }
}

export function BlockBoundary({ block, registry }: { block: { kind: string }; registry: BlockRegistry }) {
  const Render = registry[block.kind] as ((p: { block: unknown }) => JSX.Element) | undefined;
  if (!Render) return null;
  return (
    <Boundary>
      <Render block={block} />
    </Boundary>
  );
}
