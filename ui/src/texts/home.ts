// Words of Home (ui/src/home): the greeting, "waiting for you", the tenders, the message box and a dropped folder.
import { defineTexts } from "./types";

export const home = defineTexts({
  // The greeting, by the screen's clock
  morning: { en: "Good morning, {name}", ar: "صباح الخير، م. {name}" },
  evening: { en: "Good evening, {name}", ar: "مساء الخير، م. {name}" },
  morningNoName: { en: "Good morning", ar: "صباح الخير" },
  eveningNoName: { en: "Good evening", ar: "مساء الخير" },
  leftOut: {
    en: { one: "{n} tender is not in this summary.", other: "{n} tenders are not in this summary." },
    ar: {
      zero: "كل التندرات في الملخص ده.",
      one: "تندر واحد مش في الملخص ده.",
      two: "تندرين مش في الملخص ده.",
      few: "{n} تندرات مش في الملخص ده.",
      many: "{n} تندر مش في الملخص ده.",
      other: "{n} تندر مش في الملخص ده.",
    },
  },

  // Waiting for you
  waiting: { en: "Waiting for you", ar: "مستني منك" },
  homeConversation: { en: "Home conversation", ar: "محادثة الرئيسية" },
  workStopped: { en: "Work is stopped on your reply", ar: "الشغل واقف على ردّك" },

  // The tenders
  stageOf: { en: "Stage {n} of {total}: {stage}", ar: "المرحلة {n} من {total}: {stage}" },
  stagesApproved: { en: "{n} of {total} stages approved", ar: "{n} من {total} مراحل معتمدة" },
  dueToday: { en: "Due today", ar: "التقديم النهارده" },
  datePassed: { en: "Submission date passed", ar: "ميعاد التقديم عدّى" },
  noDate: { en: "No submission date", ar: "مفيش ميعاد تقديم" },
  finished: { en: "Finished", ar: "خلص" },
  confidential: { en: "Confidential", ar: "سري" },
  cannotOpen: { en: "A tender that cannot be opened", ar: "تندر مش هينفع يتفتح" },
  empty: {
    en: "No tenders yet. Drop a tender's folder in the box below and the Lead QS starts on it.",
    ar: "لسه مفيش تندرات. ارمي فولدر التندر في الصندوق تحت والـ Lead QS هيبدأ عليه.",
  },
  loadFailed: { en: "ONE could not load Home.", ar: "ONE معرفش يحمّل الرئيسية." },
  tryAgain: { en: "Try again", ar: "جرّب تاني" },

  // The message box, and what keeps the Lead from working
  placeholder: {
    en: "Write to the Lead QS, or drop a new tender's folder here",
    ar: "اكتب للـ Lead QS، أو ارمي فولدر تندر جديد هنا",
  },
  openAi: { en: "Open AI settings", ar: "افتح إعدادات الذكاء الاصطناعي" },
  openCaps: { en: "Open spending caps", ar: "افتح حدود الصرف" },
  conversationLabel: { en: "Home conversation with the Lead QS", ar: "محادثة الرئيسية مع الـ Lead QS" },

  // A dropped folder
  folderOnly: {
    en: "Drop the tender's whole folder: ONE makes a tender of it.",
    ar: "ارمي فولدر التندر كله: ONE هيعمل منه تندر.",
  },
  making: { en: "Making the tender {name}", ar: "بيعمل التندر {name}" },
  notMade: { en: "ONE could not make this tender. Try again.", ar: "ONE معرفش يعمل التندر ده. جرّب تاني." },
});
