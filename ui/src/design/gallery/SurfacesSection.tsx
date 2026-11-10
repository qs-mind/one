// Group B's demos, in the order of the specification (section 7.1). This file only lists them.
import { CardDemo } from "./surfaces/CardDemo";
import { CollapsibleDemo } from "./surfaces/CollapsibleDemo";
import { DialogDemo } from "./surfaces/DialogDemo";
import { ListRowDemo } from "./surfaces/ListRowDemo";
import { PopoverDemo } from "./surfaces/PopoverDemo";
import { ProgressDemo } from "./surfaces/ProgressDemo";
import { RailDemo } from "./surfaces/RailDemo";
import { ScrollAreaDemo } from "./surfaces/ScrollAreaDemo";
import { SectionLabelDemo } from "./surfaces/SectionLabelDemo";
import { SeparatorDemo } from "./surfaces/SeparatorDemo";
import { SkeletonDemo } from "./surfaces/SkeletonDemo";
import { StageBarDemo } from "./surfaces/StageBarDemo";
import { StatusDotDemo } from "./surfaces/StatusDotDemo";
import { TabsDemo } from "./surfaces/TabsDemo";
import { ToastsDemo } from "./surfaces/ToastsDemo";

export function SurfacesSection() {
  return (
    <div className="flex flex-col gap-10">
      <CardDemo />
      <DialogDemo />
      <PopoverDemo />
      <TabsDemo />
      <ProgressDemo />
      <StageBarDemo />
      <SkeletonDemo />
      <CollapsibleDemo />
      <RailDemo />
      <SeparatorDemo />
      <ScrollAreaDemo />
      <ToastsDemo />
      <ListRowDemo />
      <SectionLabelDemo />
      <StatusDotDemo />
    </div>
  );
}
