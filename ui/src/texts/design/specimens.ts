// The specimens' words, from the approved mockups (Main, Home, FirstLaunch, Settings), with an English pair each.
// Sample data only; words the controls and surfaces demos already hold are read from there.
import { defineTexts } from "../types";

export const specimens = defineTexts({
  // The page
  intro: {
    en: "Regions of the approved mockups, rebuilt from the real components only.",
    ar: "أجزاء من التصميمات المعتمدة، متبنية من المكونات الحقيقية بس.",
  },
  tenderSide: { en: "Tender side column", ar: "العمود الجانبي للتندر" },
  conversation: { en: "Conversation", ar: "المحادثة" },
  messageBox: { en: "Message box", ar: "صندوق الرسالة" },
  mixed: { en: "Home, first launch and settings", ar: "الرئيسية وأول فتح والإعدادات" },

  // 1. Tender side column (Main)
  tenderStatus: { en: "Tender status", ar: "حالة التندر" },
  contractsTemporary: { en: "Temporary, for this tender", ar: "مؤقت لهذا التندر" },

  // 2. Conversation (Main)
  leadOne: {
    en: "I have read the 14 files. The tender is lump sum, and submission is on the 21st. Before we start I have a note: the specification asks for two layers of insulation, and the bill of quantities says one.",
    ar: "قرأت الـ 14 ملف. التندر مقطوعية، والتسليم يوم 21. قبل ما نبدأ عندي ملاحظة: المواصفات بتطلب العزل طبقتين، وجدول الكميات مكتوب فيه طبقة واحدة.",
  },
  leadTwo: {
    en: "My view: we send the consultant a query now and price on the specification until they reply, so we lose no time.",
    ar: "رأيي نبعت استفسار للاستشاري دلوقتي ونسعّر على المواصفات لحد ما يرد، عشان ما نخسرش وقت.",
  },
  sourceSpec: { en: "Specification, page 48", ar: "المواصفات، صفحة 48" },
  priceOnBill: { en: "Price on the bill", ar: "سعّر على الجدول" },
  engineerAsks: {
    en: "Agreed. And what is your plan for the rest of the tender?",
    ar: "موافق. وإيه خطتك لباقي التندر؟",
  },
  leadPlan: {
    en: "Here is the plan, worked back from the submission date. Seven stages, and I will stop with you at the end of each one for approval.",
    ar: "دي الخطة راجعة من تاريخ التسليم. سبع مراحل، وهقف عندك في آخر كل مرحلة للاعتماد.",
  },
  contractsReading: {
    en: "The contracts engineer is reading the conditions of contract",
    ar: "مهندس العقود بيقرأ شروط العقد",
  },
  pageOf: { en: "Page {page} of {total}", ar: "صفحة {page} من {total}" },

  // 3. Message box
  messageLabel: { en: "Message to the Lead QS", ar: "رسالة للـ Lead QS" },
  messagePlaceholder: { en: "Write to the Lead QS, or drop files here", ar: "اكتب للـ Lead QS، أو ارمي ملفات هنا" },
  threeLines: { en: "Three lines", ar: "تلات سطور" },
  dropTarget: { en: "Files dragged over it", ar: "ملفات متسحبة فوقه" },

  // 4. Mixed slice (Home, FirstLaunch, Settings)
  tenders: { en: "Tenders", ar: "التندرات" },
  hospital: { en: "Hospital finishes, Makkah", ar: "تشطيبات مستشفى، مكة" },
  reviewerWorking: { en: "The review engineer is working", ar: "مهندس المراجعة شغال" },
  aboutYou: { en: "About you", ar: "عرّفني بنفسك" },
  setupLabel: { en: "Getting ONE ready", ar: "تجهيز ONE" },
  confidentialOnDevice: {
    en: "Confidential projects run on a model on this device",
    ar: "المشاريع السرية تشتغل بموديل على الجهاز",
  },
  confidentialMeta: {
    en: "Slower and weaker, but no text leaves your computer",
    ar: "أبطأ وأضعف، لكن مفيش نص بيخرج من جهازك",
  },
});
