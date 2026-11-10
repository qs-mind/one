// A meta line ("Lead QS · 14 ملف"): each part isolated in its own <bdi>, joined by a hidden dot with real spaces,
// so a Latin role name never reorders the Arabic beside it and the accessible name keeps the words apart.
import { Fragment, type ReactNode } from "react";

type MetaLineProps = { items: readonly ReactNode[]; className?: string };

export function MetaLine({ items, className }: MetaLineProps) {
  const parts = items.filter((item) => item !== null && item !== undefined && item !== false && item !== "");
  return (
    <span className={className}>
      {parts.map((item, index) => (
        // A meta line's parts have no id of their own; their order is their identity.
        <Fragment key={index}>
          {index > 0 && (
            <>
              {" "}
              <span aria-hidden="true">·</span>{" "}
            </>
          )}
          <bdi>{item}</bdi>
        </Fragment>
      ))}
    </span>
  );
}
