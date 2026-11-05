// The first step: Arabic or English, each written in its own language. The page turns with a soft wipe from the
// chosen button; the very first time the system's language is already chosen (FirstLaunch sets it).
import { language, setLanguage, t, texts, useLanguage, type Language as Lang } from "../i18n";
import { centreOf, withTransition } from "../ui/viewTransition";
import { type Nav, option, primary, StepScreen } from "./parts";

const choices: { lang: Lang; label: string }[] = [
  { lang: "ar", label: texts.languageArabic.ar },
  { lang: "en", label: texts.languageEnglish.en },
];

export function Language({ nav }: { nav: Nav }) {
  const lang = useLanguage();
  return (
    <StepScreen
      title={t("languageTitle")}
      help={t("languageHelp")}
      nav={nav}
      next={
        <button type="button" onClick={() => void nav.pass("done")} className={primary}>
          {t("setupNext")}
        </button>
      }
    >
      <div role="group" aria-label={t("languageTitle")} className="grid grid-cols-2 gap-3">
        {choices.map((choice) => (
          <button
            key={choice.lang}
            type="button"
            lang={choice.lang}
            dir={choice.lang === "ar" ? "rtl" : "ltr"}
            aria-pressed={lang === choice.lang}
            onClick={(event) =>
              language() !== choice.lang && void withTransition(() => setLanguage(choice.lang), centreOf(event.currentTarget))
            }
            className={`${option(lang === choice.lang)} py-5 text-lg`}
          >
            {choice.label}
          </button>
        ))}
      </div>
    </StepScreen>
  );
}
