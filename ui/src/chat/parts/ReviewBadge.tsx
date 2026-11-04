// The Checking QS's Review code on a Deliverable, with its comments when opened, and the Same-provider check note.
import { t, useLanguage } from "../../i18n";
import type { ReviewData } from "./types";

const names = { A: "codeA", B: "codeB", C: "codeC" } as const;

export function ReviewBadge({ review }: { review: ReviewData }) {
  useLanguage();
  const name = (
    <span className={`font-semibold ${review.code === "C" ? "text-copper" : ""}`}>{t(names[review.code])}</span>
  );
  return (
    <div className="flex flex-col gap-1 rounded-md border border-stone px-3 py-2">
      {review.comments.length > 0 ? (
        <details>
          <summary className="hover:text-copper">{name}</summary>
          <ul className="mt-2 flex flex-col gap-1">
            {review.comments.map((comment, index) => (
              <li key={index}>
                <span dir="auto" className="font-semibold">
                  {comment.about}
                </span>{" "}
                <span dir="auto">{comment.text}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : (
        name
      )}
      {review.same_provider && <p className="text-slate">{t("sameProvider")}</p>}
    </div>
  );
}
