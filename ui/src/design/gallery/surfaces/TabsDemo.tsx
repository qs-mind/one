import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/design/ui/tabs";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

export function TabsDemo() {
  const t = useText();
  return (
    <Demo id="tabs" title="Tabs">
      <State name={`${t(surfaces.stateCurrent)} · ${t(surfaces.stateHover)} · ${t(surfaces.stateFocus)} · ${t(surfaces.stateDisabled)}`}>
        <Tabs defaultValue="sheet">
          <TabsList aria-label={t(surfaces.fileViews)}>
            <TabsTrigger value="sheet">{t(surfaces.tabSheet)}</TabsTrigger>
            <TabsTrigger value="text" data-force="hover">
              {t(surfaces.tabText)}
            </TabsTrigger>
            <TabsTrigger value="notes" data-force="focus">
              {t(surfaces.tabNotes)}
            </TabsTrigger>
            <TabsTrigger value="history" disabled>
              {t(surfaces.tabHistory)}
            </TabsTrigger>
          </TabsList>
          <TabsContent value="sheet" className="pt-3">
            {t(surfaces.tabSheetBody)}
          </TabsContent>
          <TabsContent value="text" className="pt-3">
            {t(surfaces.tabTextBody)}
          </TabsContent>
          <TabsContent value="notes" className="pt-3">
            {t(surfaces.tabNotesBody)}
          </TabsContent>
        </Tabs>
      </State>
    </Demo>
  );
}
