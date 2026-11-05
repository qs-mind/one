// The last net under the whole screen: a render error anywhere shows a plain message in both languages and a Reload
// button, never a blank window. The error itself goes to the console (and so to the dev server's log), and its class
// and place in our code to Usage Stats (crash.ts).
import { Component, type ErrorInfo, type ReactNode } from "react";
import { t, texts } from "../i18n";
import { reportCrash } from "./crash";

export class ScreenError extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("The screen failed:", error, info.componentStack);
    void reportCrash(error); // its class and our file:line only, and only if the engineer shares Usage Stats
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main role="alert" className="flex h-dvh items-center justify-center bg-paper px-4">
        <div className="flex w-full max-w-xl flex-col gap-3">
          <p lang="ar" dir="rtl">
            {texts.screenFailed.ar}
          </p>
          <p lang="en" dir="ltr">
            {texts.screenFailed.en}
          </p>
          <button type="button" onClick={() => window.location.reload()} className="self-start rounded-md bg-ink px-4 py-2 text-paper">
            {t("reload")}
          </button>
        </div>
      </main>
    );
  }
}
