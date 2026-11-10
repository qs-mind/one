import { Skeleton } from "@/design/ui/skeleton";
import { common } from "@/texts/common";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

export function SkeletonDemo() {
  const t = useText();
  return (
    <Demo id="skeleton" title="Skeleton">
      <State name={t(surfaces.stateLoading)} className="flex w-full max-w-md flex-col gap-2">
        <div aria-busy="true" className="flex flex-col gap-3">
          <span className="sr-only">{t(common.loading)}</span>
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-11 w-32" />
        </div>
      </State>
    </Demo>
  );
}
