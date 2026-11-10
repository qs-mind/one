// First launch: the three steps (language, who you are, connect AI) and the setup strip under them.
import { defineTexts } from "./types";

export const firstlaunch = defineTexts({
  // Step 1. Each language is named in itself: the Arabic row shows `arabic.ar`, the English row `english.en`.
  languageTitle: { en: "Choose your language", ar: "اختار لغتك" },
  languageLead: {
    en: "ONE talks to you in it. You can change it later in Settings.",
    ar: "ONE هيكلمك بيها. تقدر تغيرها بعدين من الإعدادات.",
  },
  arabic: { en: "Arabic", ar: "العربية" },
  english: { en: "English", ar: "الإنجليزية" },

  // Step 2.
  whoTitle: { en: "Introduce yourself", ar: "عرّفني بنفسك" },
  whoLead: {
    en: "The Lead QS works with you as a colleague, so it needs to know who it is talking to.",
    ar: "الـ Lead QS هيشتغل معاك كزميل، فمحتاج يعرف هو بيكلم مين.",
  },
  signIn: { en: "Sign in with QS Mind and I fill in the name", ar: "ادخل بحساب QS Mind وأنا أملا الاسم" },
  signingIn: { en: "Finish signing in in your browser.", ar: "كمّل الدخول من المتصفح." },
  signedIn: { en: "Signed in as {email}", ar: "دخلت بحساب {email}" },
  signInFailed: {
    en: "Sign-in did not finish. Try again, or type your details.",
    ar: "الدخول مكملش. جرّب تاني، أو اكتب بياناتك.",
  },
  cancel: { en: "Cancel", ar: "إلغاء" },
  orType: { en: "or type your details", ar: "أو اكتب بياناتك" },
  fillEvery: { en: "Fill in every field to go on.", ar: "املا كل الخانات علشان تكمل." },

  // Step 3.
  aiTitle: { en: "Connect AI", ar: "وصّل الذكاء الاصطناعي" },
  aiLead: {
    en: "Paste a key from any AI provider. ONE knows the provider from the key and checks it at once.",
    ar: "الصق مفتاح من أي مزوّد ذكاء اصطناعي. ONE هيعرف المزوّد من المفتاح ويتحقق منه على طول.",
  },
  consentTitle: { en: "Before ONE uses AI", ar: "قبل ما ONE يستخدم الذكاء الاصطناعي" },
  consentBody: {
    en: "To work, ONE sends the text of your tenders and your messages to the AI provider you connect, which handles it under its own terms. Nothing is sent before you agree.",
    ar: "علشان يشتغل، ONE بيبعت نصوص العطاءات ورسايلك لمزوّد الذكاء الاصطناعي اللي هتوصّله، وهو بيتعامل معاها حسب شروطه. مفيش حاجة بتتبعت قبل ما توافق.",
  },
  terms: { en: "Terms of use", ar: "شروط الاستخدام" },
  privacy: { en: "Privacy policy", ar: "سياسة الخصوصية" },
  agree: { en: "I agree", ar: "موافق" },
  agreed: { en: "You agreed. You can read it again in Settings, Privacy.", ar: "وافقت. تقدر تقراها تاني من الإعدادات، الخصوصية." },
  consentNotSaved: { en: "Your agreement was not saved. Try again.", ar: "موافقتك متحفظتش. جرّب تاني." },
  keyLabel: { en: "Your AI key", ar: "مفتاح الذكاء الاصطناعي" },
  keyAfterConsent: { en: "Agree first, then paste the key.", ar: "وافق الأول، وبعدين الصق المفتاح." },
  keyChecking: { en: "Checking the key…", ar: "جاري التحقق من المفتاح…" },
  keyWorks: { en: "Connected to {provider}. The key works.", ar: "اتوصّل بـ {provider}. المفتاح شغال." },
  keyNotChecked: { en: "ONE could not check the key. Try again.", ar: "ONE مقدرش يتحقق من المفتاح. جرّب تاني." },
  or: { en: "or", ar: "أو" },
  useClaudeCode: { en: "Use my own Claude Code", ar: "استخدم Claude Code بتاعي" },
  claudeChecking: { en: "Checking Claude Code…", ar: "جاري التحقق من Claude Code…" },
  claudeWorks: { en: "Claude Code works. ONE uses it.", ar: "Claude Code شغال. ONE هيستخدمه." },
  claudeMissing: {
    en: "Claude Code is not on this computer. Install it and sign in to it, then try again.",
    ar: "Claude Code مش موجود على الجهاز ده. نزّله وادخل بحسابك فيه، وبعدين جرّب تاني.",
  },
  claudeFailed: { en: "Claude Code did not answer. Try again.", ar: "Claude Code مردّش. جرّب تاني." },
  tryAgain: { en: "Try again", ar: "جرّب تاني" },
  start: { en: "Start", ar: "ابدأ" },
  later: { en: "Connect later", ar: "وصّل بعدين" },
  laterNote: { en: "Without AI the Lead QS cannot work yet.", ar: "من غير ذكاء اصطناعي الـ Lead QS مش هيقدر يشتغل." },

  // Every step.
  next: { en: "Next", ar: "التالي" },
  back: { en: "Back", ar: "رجوع" },
  stepNotSaved: { en: "ONE could not save this step. Try again.", ar: "ONE مقدرش يحفظ الخطوة دي. جرّب تاني." },

  // The setup strip.
  setupGetting: { en: "ONE is getting itself ready: downloading {part}", ar: "ONE بيجهز نفسه: بينزّل {part}" },
  setupWaitsTurn: { en: "ONE is getting itself ready", ar: "ONE بيجهز نفسه" },
  setupOffline: {
    en: "Waiting for the internet to download {parts}. Everything else works.",
    ar: "مستني النت علشان ينزّل {parts}. كل حاجة تانية شغالة.",
  },
  megabytes: { en: "{done} of {total} MB", ar: "{done} من {total} ميجا" },
  notAvailable: { en: "Not available: {affects}", ar: "مش متاح دلوقتي: {affects}" },
});
