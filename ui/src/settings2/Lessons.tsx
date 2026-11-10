// What the Lead QS learned about the engineer's work (contract routes 3-5): each lesson can be rewritten (saved on
// leaving its box) or removed, with Undo in a notice for the core's window. The `lessons` event reloads the list.
import { useCallback, useEffect, useState } from "react";
import { subscribeGeneral } from "@/activity";
import { client, type Schemas } from "@/api/client";
import { undo } from "@/api/settingsKept";
import { MetaLine } from "@/design/MetaLine";
import { notify, notifyUndo } from "@/design/notify";
import { Button } from "@/design/ui/button";
import { Textarea } from "@/design/ui/textarea";
import { common } from "@/texts/common";
import { formatDate } from "@/texts/format";
import { textDir } from "@/texts/language";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

type Lesson = Schemas["Lesson"];

function LessonRow({ lesson, onRemoved }: { lesson: Lesson; onRemoved: () => void }) {
  const t = useText();
  const [typed, setTyped] = useState(lesson.text);
  const [problem, setProblem] = useState<TextPair>();
  useEffect(() => setTyped(lesson.text), [lesson.text]);

  async function save() {
    const text = typed.trim();
    if (text === "" || text === lesson.text) return setTyped(lesson.text);
    const answer = await client.PATCH("/engineer/lessons/{lesson_id}", { params: { path: { lesson_id: lesson.id } }, body: { text } }).catch(() => undefined);
    setProblem(answer?.data ? undefined : answer?.error && "error" in answer.error ? answer.error.error : texts.notSaved);
  }

  async function remove() {
    const answer = await client.DELETE("/engineer/lessons/{lesson_id}", { params: { path: { lesson_id: lesson.id } } }).catch(() => undefined);
    if (!answer?.data) return setProblem(answer?.error && "error" in answer.error ? answer.error.error : texts.notRemoved);
    const { undo: token } = answer.data;
    onRemoved();
    notifyUndo(t(texts.lessonRemoved), t(common.undo), () => void undo(token).then((back) => (back ? onRemoved() : notify(t(texts.notUndone)))));
  }

  const from = lesson.from_project_name ? t(texts.fromTender, { tender: lesson.from_project_name }) : null;
  return (
    <li className="flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <Textarea
          aria-label={t(texts.lessonLabel)}
          dir={textDir(typed)}
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          onBlur={() => void save()}
        />
        <Button variant="ghost" onClick={() => void remove()}>
          {t(texts.remove)}
        </Button>
      </div>
      <MetaLine items={[from, formatDate(new Date(lesson.at), t.lang)]} className="text-xs text-muted-foreground" />
      {problem ? (
        <p role="alert" className="text-xs font-bold">
          {t(problem)}
        </p>
      ) : null}
    </li>
  );
}

export function Lessons() {
  const t = useText();
  const [lessons, setLessons] = useState<Lesson[]>();

  const load = useCallback(async () => {
    const answer = await client.GET("/engineer/lessons").catch(() => undefined);
    if (answer?.data) setLessons(answer.data.lessons);
  }, []);

  useEffect(() => {
    const stop = subscribeGeneral((event) => event.type === "lessons" && void load(), () => void load());
    void load();
    return stop;
  }, [load]);

  if (!lessons) return null;
  return (
    <section aria-labelledby="lessons" className="flex flex-col gap-4">
      <h2 id="lessons" className="text-lg font-bold">
        {t(texts.lessons)}
      </h2>
      {lessons.length === 0 ? (
        <p className="text-muted-foreground">{t(texts.noLessons)}</p>
      ) : (
        <ul className="flex flex-col gap-5">
          {lessons.map((lesson) => (
            <LessonRow key={lesson.id} lesson={lesson} onRemoved={() => void load()} />
          ))}
        </ul>
      )}
    </section>
  );
}
