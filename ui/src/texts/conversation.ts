// Words of the conversation parts (ui/src/conversation): the thread, the Lead's message, the live line, the
// decision and plan cards, and the message box.
import { defineTexts } from "./types";

export const conversation = defineTexts({
  // Thread
  threadLabel: { en: "Conversation with the Lead QS", ar: "المحادثة مع الـ Lead QS" },
  scrollToEnd: { en: "Go to the newest message", ar: "انزل لآخر رسالة" },
  emptyTitle: { en: "Nothing here yet", ar: "لسه مفيش حاجة هنا" },
  emptyBody: {
    en: "Write to the Lead QS, or drop the tender's folder here.",
    ar: "اكتب للـ Lead QS، أو أفلت فولدر التندر هنا.",
  },
  byOne: { en: "ONE started this work", ar: "ONE بدأ الشغل ده" },
  laterPart: { en: "Updated further down", ar: "اتحدّث تحت" },

  // The Lead's message
  details: { en: "Details", ar: "التفاصيل" },
  sources: {
    en: { one: "{n} source", other: "{n} sources" },
    ar: {
      zero: "مفيش مصادر",
      one: "مصدر واحد",
      two: "مصدرين",
      few: "{n} مصادر",
      many: "{n} مصدر",
      other: "{n} مصدر",
    },
  },
  sourcePage: { en: "{title}, page {page}", ar: "{title}، صفحة {page}" },
  sourceItem: { en: "{title}, item {item}", ar: "{title}، بند {item}" },
  sourceRow: { en: "{title}, row {row}", ar: "{title}، صف {row}" },

  // The live line and its work log
  workLog: { en: "Work log", ar: "سجل الشغل" },
  logEmpty: { en: "No steps yet", ar: "لسه مفيش خطوات" },
  stepDone: { en: "Finished", ar: "خلصت" },
  stepRunning: { en: "Running", ar: "شغّالة" },

  // Decision card
  needsYou: { en: "{name} needs your decision", ar: "{name} محتاج قرارك" },
  opinion: { en: "Recommendation", ar: "الرأي" },
  queued: { en: "Next after the current decision: {title}", ar: "بعد القرار الحالي: {title}" },
  chose: { en: "You chose: {option}", ar: "اخترت: {option}" },
  holdPaid: { en: "This choice starts paid work", ar: "الاختيار ده بيبدأ شغل مدفوع" },
  holdIrreversible: { en: "This choice cannot be taken back", ar: "الاختيار ده مايترجعش فيه" },

  // Plan card
  planTitle: { en: "Tender plan", ar: "خطة التندر" },
  stageCount: {
    en: { one: "{n} stage", other: "{n} stages" },
    ar: { zero: "مفيش مراحل", one: "مرحلة واحدة", two: "مرحلتين", few: "{n} مراحل", many: "{n} مرحلة", other: "{n} مرحلة" },
  },
  dayCount: {
    en: { one: "{n} day", other: "{n} days" },
    ar: { zero: "ولا يوم", one: "يوم واحد", two: "يومين", few: "{n} أيام", many: "{n} يوم", other: "{n} يوم" },
  },
  minutes: {
    en: { one: "about {n} minute of AI work", other: "about {n} minutes of AI work" },
    ar: {
      zero: "أقل من دقيقة شغل ذكاء اصطناعي",
      one: "حوالي دقيقة شغل ذكاء اصطناعي",
      two: "حوالي دقيقتين شغل ذكاء اصطناعي",
      few: "حوالي {n} دقايق شغل ذكاء اصطناعي",
      many: "حوالي {n} دقيقة شغل ذكاء اصطناعي",
      other: "حوالي {n} دقيقة شغل ذكاء اصطناعي",
    },
  },
  cost: { en: "Expected cost {cost}", ar: "التكلفة المتوقعة {cost}" },
  costUnknown: { en: "Cost not known yet", ar: "التكلفة لسه مش معروفة" },
  submission: { en: "Submission {date}", ar: "التسليم {date}" },
  stageBar: { en: "Stage {step} of {total}: {name}", ar: "المرحلة {step} من {total}: {name}" },
  stageBarNone: { en: "No stage has started yet", ar: "لسه ولا مرحلة بدأت" },
  stageBarDone: { en: "Every stage is signed off", ar: "كل المراحل اتعتمدت" },
  approve: { en: "Approve and start", ar: "وافق وابدأ" },
  planBusy: { en: "The Lead is still writing. You can answer once it ends.", ar: "الـ Lead لسه بيكتب. تقدر ترد أول ما يخلص." },
  approveHint: { en: "Approving starts paid work", ar: "الموافقة بتبدأ شغل مدفوع" },
  discuss: { en: "Discuss the plan", ar: "ناقش الخطة" },
  approvedOn: { en: "Approved {date}", ar: "اتوافق عليها {date}" },
  replaced: { en: "Replaced by version {n}", ar: "اتبدّلت بالنسخة {n}" },
  changeTitle: { en: "Suggested change", ar: "تعديل مقترح" },
  changeNow: { en: "Now", ar: "دلوقتي" },
  changeAfter: { en: "Suggested", ar: "المقترح" },
  acceptChange: { en: "Accept the change", ar: "اقبل التعديل" },
  acceptChangeHint: { en: "The changed plan runs paid work", ar: "الخطة بعد التعديل بتشغّل شغل مدفوع" },
  rejectChange: { en: "Keep the plan as it is", ar: "سيب الخطة زي ما هي" },

  // Message box
  messageLabel: { en: "Message to the Lead QS", ar: "رسالة للـ Lead QS" },
  placeholder: { en: "Write to the Lead QS", ar: "اكتب للـ Lead QS" },
  folder: { en: "Folder {name}", ar: "فولدر {name}" },
  remove: { en: "Remove {name}", ar: "شيل {name}" },
  steeringTitle: { en: "Going to the Lead QS", ar: "رايحة للـ Lead QS" },
  whileWorking: {
    en: "The Lead QS is working. Your message goes now and steers this work.",
    ar: "الـ Lead QS شغّال. رسالتك هتوصله دلوقتي وهيوجّه بيها الشغل ده.",
  },
  whileHeld: { en: "The Lead QS reads this after your choice.", ar: "الـ Lead QS هيقرا ده بعد اختيارك." },
  steerFailed: { en: "Not sent. The Lead QS has not read it.", ar: "متبعتتش. الـ Lead QS ماقراهاش." },
  steerAgain: { en: "Send again", ar: "ابعت تاني" },
  dropSteer: { en: "Drop this message", ar: "شيل الرسالة دي" },
});
