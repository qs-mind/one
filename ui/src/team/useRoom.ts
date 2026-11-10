// A tender's team room: GET /projects/{id}/room in pages, newest first, kept current by the `room` event (contract
// 3.4: replace a message held by id; add one only if it is newer than the newest held). The engineer's message is
// POST /projects/{id}/room, whose answer is the stored message, shown at once.
import { useCallback, useEffect, useRef, useState } from "react";
import { subscribeTender } from "@/activity";
import { client, type Schemas } from "@/api/client";
import { wordsOf } from "./useTeam";

export type RoomMessage = Schemas["RoomMessage"];
type Text = Schemas["Text"];

export const PAGE = 50;

export type RoomState =
  | { state: "loading" }
  | { state: "ready"; messages: RoomMessage[]; cursor: string | null; older: boolean }
  | { state: "failed"; error: Text | null };

/** A message from the core into the held list (newest first): it replaces its own copy, or comes first when it is
 * newer than the newest held. One older than that is left to the pages that hold it. */
export function place(messages: readonly RoomMessage[], message: RoomMessage): RoomMessage[] {
  const at = messages.findIndex((it) => it.id === message.id);
  if (at >= 0) return messages.with(at, message);
  const newest = messages[0];
  return newest === undefined || message.at > newest.at ? [message, ...messages] : [...messages];
}

export type Sent = { ok: true } | { ok: false; error: Text | null };

export function useRoom(projectId: string) {
  const [room, setRoom] = useState<RoomState>({ state: "loading" });
  const [round, setRound] = useState(0);
  const roomRef = useRef(room);
  roomRef.current = room;

  const page = useCallback(
    (cursor?: string) =>
      client.GET("/projects/{project_id}/room", {
        params: { path: { project_id: projectId }, query: cursor ? { cursor, limit: PAGE } : { limit: PAGE } },
      }),
    [projectId],
  );

  useEffect(() => {
    let live = true;
    const load = () =>
      void page()
        .then(({ data, error }) => {
          if (!live) return;
          setRoom(
            data
              ? { state: "ready", messages: data.messages, cursor: data.next_cursor, older: false }
              : { state: "failed", error: wordsOf(error) },
          );
        })
        .catch(() => live && setRoom({ state: "failed", error: null }));
    const stop = subscribeTender(
      projectId,
      (event) => {
        if (!live || event.type !== "room") return;
        setRoom((now) => (now.state === "ready" ? { ...now, messages: place(now.messages, event.message) } : now));
      },
      load,
    );
    load();
    return () => {
      live = false;
      stop();
    };
  }, [projectId, page, round]);

  /** The next older page, after the oldest held. A cursor the core no longer knows opens the room again. */
  const loadOlder = useCallback(async () => {
    const now = roomRef.current;
    if (now.state !== "ready" || now.cursor === null || now.older) return;
    setRoom({ ...now, older: true });
    const answer = await page(now.cursor).catch(() => undefined);
    if (answer?.data) {
      const older = answer.data.messages;
      setRoom((it) =>
        it.state === "ready"
          ? { ...it, messages: [...it.messages, ...older.filter((m) => !it.messages.some((h) => h.id === m.id))], cursor: answer.data.next_cursor, older: false }
          : it,
      );
    } else if (answer?.response.status === 422) setRound((n) => n + 1);
    else setRoom((it) => (it.state === "ready" ? { ...it, older: false } : it));
  }, [page]);

  const send = useCallback(
    async (text: string): Promise<Sent> => {
      const answer = await client
        .POST("/projects/{project_id}/room", { params: { path: { project_id: projectId } }, body: { text } })
        .catch(() => undefined);
      if (!answer?.data) return { ok: false, error: wordsOf(answer?.error) };
      const message = answer.data;
      setRoom((now) => (now.state === "ready" ? { ...now, messages: place(now.messages, message) } : now));
      return { ok: true };
    },
    [projectId],
  );

  return { room, loadOlder, send, reload: () => setRound((n) => n + 1) };
}
