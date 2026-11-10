// Group A's demos, in the order of the specification (section 7.1). This file only lists them.
import { ButtonDemo } from "./controls/ButtonDemo";
import { CheckboxDemo } from "./controls/CheckboxDemo";
import { FieldDemo } from "./controls/FieldDemo";
import { HoldButtonDemo } from "./controls/HoldButtonDemo";
import { InputDemo } from "./controls/InputDemo";
import { LabelDemo } from "./controls/LabelDemo";
import { PillDemo } from "./controls/PillDemo";
import { RadioGroupDemo } from "./controls/RadioGroupDemo";
import { SelectDemo } from "./controls/SelectDemo";
import { TextareaDemo } from "./controls/TextareaDemo";
import { TooltipDemo } from "./controls/TooltipDemo";

export function ControlsSection() {
  return (
    <div className="flex flex-col gap-10">
      <ButtonDemo />
      <HoldButtonDemo />
      <InputDemo />
      <TextareaDemo />
      <SelectDemo />
      <RadioGroupDemo />
      <CheckboxDemo />
      <LabelDemo />
      <FieldDemo />
      <TooltipDemo />
      <PillDemo />
    </div>
  );
}
