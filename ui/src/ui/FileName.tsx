// A file name, shown so that a name mixing Arabic and Latin reads in order. The whole name is isolated from the text
// around it and takes its direction from its own first letter; the extension is isolated left to right, so
// «مواصفات (sample spec).docx» reads «مواصفات (sample spec)» then «.docx», not «docx.(sample spec) مواصفات».
const EXTENSION = /(\.[A-Za-z0-9]{1,8})$/;

export function splitName(name: string): [stem: string, extension: string] {
  const found = EXTENSION.exec(name);
  return found && found.index > 0 ? [name.slice(0, found.index), found[1]!] : [name, ""];
}

export function FileName({ name, className }: { name: string; className?: string }) {
  const [stem, extension] = splitName(name);
  return (
    <bdi dir="auto" className={className}>
      {stem}
      {extension && <bdi dir="ltr">{extension}</bdi>}
    </bdi>
  );
}
