// The foundation demos, in the order of the specification (section 7.1). This file only lists them.
import { Colours } from "./foundation/Colours";
import { Density } from "./foundation/Density";
import { Icons } from "./foundation/Icons";
import { MetaNum } from "./foundation/MetaNum";
import { NowWaiting } from "./foundation/NowWaiting";
import { Radius } from "./foundation/Radius";
import { Space } from "./foundation/Space";
import { Type } from "./foundation/Type";
import { WordmarkDemo } from "./foundation/WordmarkDemo";

export function FoundationSection() {
  return (
    <div className="flex flex-col gap-10">
      <Colours />
      <Type />
      <Space />
      <Radius />
      <Icons />
      <Density />
      <NowWaiting />
      <MetaNum />
      <WordmarkDemo />
    </div>
  );
}
