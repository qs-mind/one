"""A Brief's work log: each step its team reported, when it began and ended, and when the Brief
began and ended. The screen settles its Thinking line to these real times ("Worked for 2m · 6
steps") and gives a running step its own timer; nothing there is guessed.

A step is one Progress event. A tool call (`Progress.tool`) is a new step that stays open until
its agent's tools return, so the calls of one answer run side by side; any other Progress from an
agent whose tool is still running only updates that step's words (a tool saying which pages it
reads). A plain step ends when the same agent's next step begins. The Brief's end closes every
step. Times are ISO 8601 UTC from the engine's clock."""

import json
from dataclasses import dataclass, field

from qsone.engine.types import Progress


@dataclass
class WorkLog:
    started: str
    ended: str | None = None
    steps: list[dict] = field(default_factory=list)  # {run, agent, text, at, until, tool}

    def _open(self, run_id: str) -> list[dict]:
        return [s for s in self.steps if s["run"] == run_id and s["until"] is None]

    def add(self, event: Progress, at: str) -> None:
        open_ = self._open(event.run_id)
        if not event.tool and open_ and open_[-1]["tool"]:
            open_[-1]["text"] = event.text
            return
        for s in open_:
            if not s["tool"] or not event.tool:
                s["until"] = at
        self.steps.append(
            {
                "run": event.run_id,
                "agent": event.agent,
                "text": event.text,
                "at": at,
                "until": None,
                "tool": event.tool,
            }
        )

    def tools_done(self, run_id: str, at: str) -> bool:
        """Ends the run's open tool steps; True when one ended."""
        done = [s for s in self._open(run_id) if s["tool"]]
        for s in done:
            s["until"] = at
        return bool(done)

    def end(self, at: str) -> None:
        for s in self.steps:
            if s["until"] is None:
                s["until"] = at
        self.ended = at

    def as_json(self) -> dict:
        """What the screen gets, as the `data-worklog` part."""
        steps = [{k: s[k] for k in ("agent", "text", "at", "until")} for s in self.steps]
        return {"started": self.started, "ended": self.ended, "steps": steps}

    def saved(self) -> str:
        return json.dumps(
            {"started": self.started, "ended": self.ended, "steps": self.steps},
            ensure_ascii=False,
        )

    @classmethod
    def load(cls, text: str, *, stopped_at: str) -> "WorkLog":
        """A saved log, to go on with. A step still open was cut off when the core stopped: it
        ends at `stopped_at`, the last time the core wrote the Brief."""
        data = json.loads(text)
        log = cls(started=data["started"], ended=data.get("ended"), steps=list(data["steps"]))
        for s in log.steps:
            if s["until"] is None:
                s["until"] = stopped_at
        log.ended = None
        return log
