// Project files (files:all) as the open document: Project Records without its panel chrome. Files dropped or added go
// to Project Records; a file opens as the workspace's document.
import { RecordsPanel } from "../../records/RecordsPanel";

export function FilesDoc() {
  return <RecordsPanel layout="document" />;
}
