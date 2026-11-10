// The frame around the three places: the rail on the start side, the place beside it. First launch has no frame.
// The rail's Tenders item opens the tender open now or opened last in this session, else the core's last opened
// tender (Home.last_project_id), else Home, where the tenders are listed.
import { HouseIcon, LayersIcon, SettingsIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, matchPath, Outlet, useLocation } from "react-router";
import { client } from "@/api/client";
import { Rail, type RailItem } from "@/design/Rail";
import { common } from "@/texts/common";
import { useText } from "@/texts/useText";
import { paths } from "./paths";

type Place = "home" | "tender" | "settings";

const placeOf = (pathname: string): Place =>
  pathname.startsWith("/tender/") ? "tender" : pathname.startsWith("/settings") ? "settings" : "home";

function useLastTender(pathname: string): string | null {
  const open = matchPath("/tender/:id/*", pathname)?.params.id ?? null;
  const [seen, setSeen] = useState<string | null>(null);
  const [fromCore, setFromCore] = useState<string | null>(null);

  useEffect(() => {
    if (open) setSeen(open);
  }, [open]);

  useEffect(() => {
    let live = true;
    client
      .GET("/home")
      .then(({ data }) => live && setFromCore(data?.last_project_id ?? null))
      .catch(() => undefined); // no core: the item leads to Home
    return () => {
      live = false;
    };
  }, []);

  return open ?? seen ?? fromCore;
}

export function Frame() {
  const t = useText();
  const { pathname } = useLocation();
  const place = placeOf(pathname);
  const tender = useLastTender(pathname);

  const item = (id: Place, label: string, icon: RailItem["icon"], to: string): RailItem => ({
    id,
    label,
    icon,
    current: place === id,
    render: <Link to={to} />,
  });
  const items = [
    item("home", t(common.home), HouseIcon, paths.home),
    item("tender", t(common.tenders), LayersIcon, tender ? paths.tender(tender) : paths.home),
  ];

  return (
    <div className="flex h-dvh bg-background text-foreground">
      <Rail label={t(common.navigation)} items={items} footerItems={[item("settings", t(common.settings), SettingsIcon, paths.settings())]} />
      <div className="min-w-0 flex-1 overflow-auto">
        <Outlet />
      </div>
    </div>
  );
}
