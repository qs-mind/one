// A file name, shown so that a name mixing Arabic and Latin reads in order. The whole name is isolated from the text
// around it and takes its direction from its own first letter; the extension is isolated left to right, so
// «مواصفات (sample spec).docx» reads «مواصفات (sample spec)» then «.docx», not «docx.(sample spec) مواصفات».
// In a list (`fit`) the name keeps to one line: a name too long for its place loses the end of its stem to «…» while
// its extension stays whole after it, «جدول كميات - عينة اخ….xlsx», and the full name is its tooltip.
const EXTENSION = /(\.[A-Za-z0-9]{1,8})$/;

export function splitName(name: string): [stem: string, extension: string] {
  const found = EXTENSION.exec(name);
  return found && found.index > 0 ? [name.slice(0, found.index), found[1]!] : [name, ""];
}

export function FileName({ name, className = "", fit = false }: { name: string; className?: string; fit?: boolean }) {
  const [stem, extension] = splitName(name);
  if (fit) {
    return (
      <bdi dir="auto" title={name} data-file-name className={`inline-flex min-w-0 max-w-full ${className}`}>
        <span className="min-w-0 truncate">{stem}</span>
        {extension && (
          <bdi dir="ltr" className="shrink-0 whitespace-nowrap">
            {extension}
          </bdi>
        )}
      </bdi>
    );
  }
  return (
    <bdi dir="auto" className={className || undefined}>
      {stem}
      {extension && (
        <bdi dir="ltr" className="whitespace-nowrap">
          {extension}
        </bdi>
      )}
    </bdi>
  );
}
