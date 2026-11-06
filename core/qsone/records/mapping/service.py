"""One background map worker for open projects, yielding between file/page slices."""

import logging
import threading

from qsone.records.mapping import worker

log = logging.getLogger(__name__)


class Mapping:
    def __init__(self, projects, *, foreground=lambda project_id: False):
        self.projects = projects
        self.foreground = foreground
        self._quit = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._original = worker.FilePass()

    def start(self):
        self._thread = threading.Thread(target=self._work, name="qsone-map-worker", daemon=True)
        self._thread.start()

    def wake(self):
        self._wake.set()

    def stop(self):
        self._quit.set()
        self._wake.set()
        if self._thread:
            # Finish the current bounded OCR/structure call before Records is closed.
            self._thread.join()
        self._original.clear()

    def _work(self):
        while not self._quit.is_set():
            self._wake.clear()
            worked = False
            opened = self.projects.opened()
            if self._original.key is not None:
                current = self._original.key[0]
                if not any(rec is current for _, rec in opened):
                    self._original.clear()
                else:
                    # Keep one file's original through its page slices before
                    # switching projects, rather than decrypting both every turn.
                    opened.sort(key=lambda pair: pair[1] is not current)
            for pid, rec in opened:
                if self._quit.is_set():
                    break
                if self.foreground(pid):
                    continue
                try:
                    worked = (
                        worker.step(
                            rec,
                            original=self._original,
                            cancelled=lambda pid=pid: self._quit.is_set() or self.foreground(pid),
                        )
                        or worked
                    )
                    if worked:
                        break
                except Exception as error:
                    # A project may close between opened() and the slice. No private content logged.
                    self._original.clear()
                    log.warning(
                        "Map slice interrupted: project=%s cause=%s", pid, type(error).__name__
                    )
            self._wake.wait(0.05 if worked else 5)
