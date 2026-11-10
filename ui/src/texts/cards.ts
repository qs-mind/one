// Words of what the engineer answers in a thread (ui/src/conversation): a card a running Brief waits on, a stage's
// sign-off block and work that was cut off; and what the thread says when a message got no answer.
import { defineTexts } from "./types";

/** Each card option's words, by the option's id: what the answer does, never a bare id. */
export const cardOption = defineTexts({
  yes: { en: "Yes", ar: "أيوه" },
  no: { en: "No", ar: "لأ" },
  allowOnce: { en: "Allow once", ar: "اسمح المرة دي" },
  allowBrief: { en: "Allow for this work", ar: "اسمح للشغل ده كله" },
  dontAllow: { en: "Don't allow", ar: "ماتسمحش" },
  capContinue: { en: "Continue to the cap", ar: "كمّل لحد السقف" },
  capRaise: { en: "Raise the cap", ar: "ارفع السقف" },
  capReport: { en: "Stop with a report", ar: "اقف بتقرير" },
  useIt: { en: "Use it", ar: "استخدمه" },
  dontUseIt: { en: "Don't use it", ar: "ماتستخدموش" },
  enterItsPrice: { en: "Enter its price", ar: "اكتب سعره" },
  useWithoutPrice: { en: "Use it without a price", ar: "استخدمه من غير سعر" },
  start: { en: "Start", ar: "ابدأ" },
  dontStart: { en: "Don't start", ar: "ماتبدأش" },
  keepDesk: { en: "Keep the Desk", ar: "احتفظ بالقسم" },
  dontKeep: { en: "Don't keep it", ar: "ماتحتفظش بيه" },
  keepAsIs: { en: "Keep it as it is", ar: "سيبه زي ما هو" },
  sendBack: { en: "No, send it back to be fixed", ar: "لأ، رجّعه يتصلّح" },
  send: { en: "Send", ar: "ابعت" },
  keepForAll: { en: "Keep it for all projects", ar: "احفظه لكل المشاريع" },
  keepTicked: { en: "Keep the ticked rows", ar: "احفظ الصفوف المعلّمة" },
  keepNone: { en: "Don't keep any", ar: "ماتحفظش حاجة" },
  goAhead: { en: "Go ahead", ar: "كمّل" },
  notNow: { en: "Not now", ar: "مش دلوقتي" },
  addIt: { en: "Add it", ar: "ضيفه" },
  dontAdd: { en: "Don't add it", ar: "ماتضيفوش" },
  keepMember: { en: "Keep on the team", ar: "خليه في الفريق" },
  dontKeepMember: { en: "Only for this tender", ar: "لهذا التندر بس" },
  saveSetting: { en: "Change it", ar: "غيّره" },
  dontSaveSetting: { en: "Leave it as it is", ar: "سيبه زي ما هو" },
});

export const cards = defineTexts({
  // A card
  answered: { en: "Your answer: {choice}", ar: "ردّك: {choice}" },
  withdrawn: { en: "No longer needed", ar: "مبقاش له لازمة" },
  noAnswers: { en: "sent with no answers", ar: "اتبعت من غير ردود" },
  notSent: { en: "Your answer was not sent. Try again.", ar: "ردّك موصلش. جرّب تاني." },
  holdPaid: { en: "Press and hold to go ahead: this costs money", ar: "اضغط مطوّل عشان تكمّل: ده بيكلّف فلوس" },
  holdIrreversible: {
    en: "Press and hold to go ahead: this cannot be taken back",
    ar: "اضغط مطوّل عشان تكمّل: ده مايترجعش فيه",
  },
  raiseGo: { en: "Go on with the new caps", ar: "كمّل بالسقف الجديد" },
  answer: { en: "Your answer", ar: "ردّك" },

  // A table card: prices to keep, a BOQ import's columns
  keepColumns: { en: "Import with these columns", ar: "استورد بالأعمدة دي" },
  checkColumns: { en: "Check the columns", ar: "راجع الأعمدة" },
  hideColumns: { en: "Hide the columns", ar: "اخفي الأعمدة" },
  columnMeaning: { en: "What column {letter} holds", ar: "العمود {letter} فيه إيه" },
  tickRow: { en: "Keep row {n}", ar: "احفظ الصف {n}" },
  sourceOf: { en: "Source of {value}", ar: "مصدر {value}" },

  // A Connector being added
  readWithoutAsking: { en: "Use its reading tools without asking me", ar: "استخدم أدوات القراية بتاعته من غير ما تسألني" },
  readWithoutAskingHelp: {
    en: "Only tools it marks as reading only. Once work has read outside text, ONE asks again.",
    ar: "بس الأدوات اللي معلّم عليها إنها للقراية بس. ولما الشغل يقرا نص من برّه، ONE بيسأل تاني.",
  },
  useForSearch: { en: "Use for web search", ar: "استخدمه للبحث في الويب" },
  noSearchTool: { en: "Not for web search", ar: "مش للبحث في الويب" },
  toolReadsOnly: { en: "Reads only", ar: "قراية بس" },
  toolActs: { en: "Can send or change things: asks you every time", ar: "يقدر يبعت أو يغيّر حاجات: بيسألك كل مرة" },
  toolDeletes: { en: "Can delete: asks you every time", ar: "يقدر يمسح: بيسألك كل مرة" },
  toolOpenWorld: { en: "Reaches outside services: asks you every time", ar: "بيوصل لخدمات برّه: بيسألك كل مرة" },

  // A model with no known price
  priceIn: { en: "Input, USD per million tokens", ar: "الداخل، دولار لكل مليون توكن" },
  priceOut: { en: "Output, USD per million tokens", ar: "الخارج، دولار لكل مليون توكن" },
  useThisPrice: { en: "Use it at this price", ar: "استخدمه بالسعر ده" },
  priceNotSaved: { en: "The price was not saved. Try again.", ar: "السعر ماتحفظش. جرّب تاني." },
  capsNotLoaded: { en: "The caps could not be read. Raise them in Settings.", ar: "الحدود ماتقريتش. ارفعها من الإعدادات." },

  // A stage's sign-off block
  stageAsks: { en: "Sign off «{stage}»", ar: "اعتمد «{stage}»" },
  gate: { en: "What you sign off", ar: "اللي بتعتمده" },
  outputs: { en: "What this stage made", ar: "اللي المرحلة دي طلّعته" },
  notReady: { en: "not ready yet", ar: "لسه مش جاهز" },
  signOff: { en: "Sign off", ar: "اعتمد" },
  signOffHint: { en: "A sign-off cannot be taken back", ar: "الاعتماد مايترجعش فيه" },
  notes: { en: "I have notes", ar: "عندي ملاحظات" },
  signedOff: { en: "«{stage}» is signed off", ar: "«{stage}» اتعتمدت" },
  stageWorking: { en: "Work on «{stage}» goes on", ar: "الشغل على «{stage}» مكمّل" },
  stageGone: { en: "This stage is no longer in the plan", ar: "المرحلة دي مبقتش في الخطة" },

  // Work that was cut off
  unfinishedLine: { en: "Work was cut off when ONE closed", ar: "الشغل اتقطع لما ONE اتقفل" },
  continue: { en: "Continue", ar: "كمّل" },
  leave: { en: "Leave it", ar: "سيبه" },

  // A message that got no answer
  workFailed: { en: "This work did not finish", ar: "الشغل ده ماخلصش" },
  noAnswer: { en: "Your message got no answer. Try again.", ar: "رسالتك ماجالهاش رد. جرّب تاني." },
  messageNotSent: {
    en: "Your message was not sent: other work is running and did not take it. Try again.",
    ar: "رسالتك ماتبعتتش: فيه شغل تاني شغّال وماخدهاش. جرّب تاني.",
  },
  filesIn: {
    en: { one: "{n} file went into the tender", other: "{n} files went into the tender" },
    ar: {
      zero: "مفيش ملفات دخلت التندر",
      one: "ملف واحد دخل التندر",
      two: "ملفين دخلوا التندر",
      few: "{n} ملفات دخلت التندر",
      many: "{n} ملف دخلوا التندر",
      other: "{n} ملف دخلوا التندر",
    },
  },
  filesNotIn: { en: "The files did not go into the tender. Drop them again.", ar: "الملفات مادخلتش التندر. أفلتها تاني." },

  // The team's messages in the work log
  roomTo: { en: "to {name}", ar: "لـ{name}" },
  you: { en: "You", ar: "إنت" },
  team: { en: "the team", ar: "الفريق" },
  member: { en: "a team member", ar: "حد من الفريق" },
  leadName: { en: "Lead QS", ar: "الـ Lead QS" },
});
