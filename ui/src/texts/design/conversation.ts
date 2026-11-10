// Texts of the conversation parts' gallery page (dev only). Everything the Lead or the engineer "says" here is sample
// data and says so.
import { defineTexts } from "../types";

export const conversationGallery = defineTexts({
  view: { en: "Conversation", ar: "المحادثة" },
  intro: {
    en: "The conversation parts of a tender, drawn from the contract's sample data.",
    ar: "أجزاء محادثة التندر، مرسومة من بيانات العينة بتاعة العقد.",
  },
  thread: { en: "Thread", ar: "المحادثة" },
  leadMessage: { en: "The Lead's message", ar: "رسالة الـ Lead" },
  liveLine: { en: "Live line", ar: "سطر الشغل الحالي" },
  decisionCard: { en: "Decision card", ar: "كارت القرار" },
  planCard: { en: "Plan card", ar: "كارت الخطة" },
  composer: { en: "Message box", ar: "صندوق الرسالة" },
  short: { en: "Four lines or fewer", ar: "أربع سطور أو أقل" },
  folded: { en: "Longer: the rest under Details", ar: "أطول: الباقي تحت التفاصيل" },
  waiting: { en: "Waiting, with a hold", ar: "مستني، بضغطة مطوّلة" },
  queuedState: { en: "A second one waits", ar: "واحد تاني مستني" },
  settled: { en: "Settled", ar: "اتحسم" },
  proposed: { en: "Proposed", ar: "مقترحة" },
  withChange: { en: "Approved, with a suggested change", ar: "معتمدة، وفيها تعديل مقترح" },
  replacedState: { en: "An older version", ar: "نسخة أقدم" },
  idle: { en: "The Lead is free", ar: "الـ Lead فاضي" },
  working: { en: "The Lead is working", ar: "الـ Lead شغّال" },
  held: { en: "The work waits for a choice", ar: "الشغل مستني اختيار" },
  sent: { en: "Sent: {text}", ar: "اتبعتت: {text}" },

  // What the Lead and the engineer say: sample data
  leadRead: {
    en: "I read the 14 files (sample).\nThe tender is a lump sum, due on the 21st (sample).\nOne point first: the specification asks for two layers of insulation (sample).\nThe bill of quantities says one (sample).\nThe specification governs where they conflict (sample).\nI would ask the consultant now and price on the specification until they answer (sample).",
    ar: "قريت الـ 14 ملف - عينة.\nالتندر مقطوعية، والتسليم يوم 21 - عينة.\nعندي ملاحظة الأول: المواصفات بتطلب العزل طبقتين - عينة.\nوجدول الكميات مكتوب فيه طبقة واحدة - عينة.\nالمواصفات هي اللي بتحكم عند التعارض - عينة.\nرأيي نبعت استفسار للاستشاري دلوقتي ونسعّر على المواصفات لحد ما يرد - عينة.",
  },
  leadShort: {
    en: "The plan works back from the submission date. Seven stages; I stop with you at the end of each (sample).",
    ar: "دي الخطة راجعة من تاريخ التسليم. سبع مراحل، وهقف عندك في آخر كل مرحلة - عينة.",
  },
  engineerAsks: { en: "Agreed. What is your plan for the rest (sample)?", ar: "موافق. وإيه خطتك لباقي التندر؟ - عينة" },
  steer: { en: "Start with the first concrete section (sample)", ar: "ابدأ بقسم الخرسانة الأول - عينة" },
  agent: { en: "Contracts engineer (sample)", ar: "مهندس العقود - عينة" },
  reading: { en: "Reading the conditions of contract, page 12 of 64 (sample)", ar: "بيقرأ شروط العقد، صفحة 12 من 64 - عينة" },
  readingLater: { en: "Reading the conditions of contract, page 13 of 64 (sample)", ar: "بيقرأ شروط العقد، صفحة 13 من 64 - عينة" },
  leadAgent: { en: "Lead QS (sample)", ar: "Lead QS - عينة" },
  stepFiles: { en: "Read the 14 files (sample)", ar: "قرا الـ 14 ملف - عينة" },
  stepPlan: { en: "Wrote the plan (sample)", ar: "كتب الخطة - عينة" },
  stepConditions: { en: "Conditions of contract (sample)", ar: "شروط العقد - عينة" },
  paidOption: { en: "Order the survey (sample)", ar: "اطلب المسح - عينة" },
  freeOption: { en: "Use the drawings (sample)", ar: "استخدم اللوحات - عينة" },
  paidTitle: { en: "Survey the site before pricing (sample)", ar: "مسح الموقع قبل التسعير - عينة" },
});
