// Sample texts of the surfaces demos and their tests (dev only). Every one is sample data.
import { defineTexts } from "../types";

export const surfaces = defineTexts({
  // States shown side by side in a demo
  stateRest: { en: "At rest", ar: "عادي" },
  stateHover: { en: "Hover", ar: "تحت المؤشر" },
  stateFocus: { en: "Focus", ar: "تركيز" },
  stateCurrent: { en: "Current", ar: "الحالي" },
  stateDisabled: { en: "Disabled", ar: "معطّل" },
  stateEmpty: { en: "No value yet", ar: "من غير قيمة لسه" },
  stateLoading: { en: "Loading", ar: "جاري التحميل" },
  stateClosed: { en: "Closed", ar: "مقفول" },
  stateOpen: { en: "Open", ar: "مفتوح" },

  // Card
  planTitle: { en: "Tender plan", ar: "خطة التندر" },
  planBody: {
    en: "Seven stages, from reading the documents to handing over.",
    ar: "سبع مراحل، من قراءة المستندات لحد التسليم.",
  },
  stageCount: { en: "{n} stages", ar: "{n} مراحل" },
  planDays: { en: "{n} days", ar: "{n} يوم" },
  discussPlan: { en: "Discuss the plan", ar: "ناقش الخطة" },
  agree: { en: "Agree", ar: "موافق" },
  sourceTitle: { en: "Bill of quantities, item 7/03", ar: "جدول الكميات، بند 7/03" },
  sourceBody: { en: "Reinforced concrete for the ground beams.", ar: "خرسانة مسلحة للميدات." },
  waitingLine: { en: "Lead QS raised this for you", ar: "Lead QS طلّع ده للمهندس" },
  providerTitle: { en: "[The connected provider]", ar: "[المزود المتصل]" },
  providerMeta: { en: "Connected, checked a moment ago", ar: "متصل، اتراجع من لحظة" },

  // Dialog
  restoreOpen: { en: "Restore a backup", ar: "استرجاع نسخة احتياطية" },
  restoreTitle: { en: "Restore the backup of 21 November?", ar: "استرجاع نسخة 21 نوفمبر؟" },
  restoreBody: {
    en: "The tender goes back to how it was that day. Work done since then stays in the backup folder.",
    ar: "التندر هيرجع زي ما كان اليوم ده. الشغل اللي اتعمل بعدها يفضل في فولدر النسخ.",
  },
  restore: { en: "Restore", ar: "استرجع" },
  cancel: { en: "Cancel", ar: "إلغاء" },

  // Popover
  workLog: { en: "Work log", ar: "سجل الشغل" },
  workLogTitle: { en: "What the team did", ar: "الفريق عمل إيه" },
  workLogBody: {
    en: "The contracts engineer read the conditions of contract.",
    ar: "مهندس العقود قرأ شروط العقد.",
  },

  // Tabs
  tabSheet: { en: "Sheet", ar: "الجدول" },
  tabText: { en: "Text", ar: "النص" },
  tabNotes: { en: "Notes", ar: "الملاحظات" },
  tabHistory: { en: "History", ar: "السجل" },
  tabSheetBody: { en: "The rows of the bill of quantities.", ar: "بنود جدول الكميات." },
  tabTextBody: { en: "The file as text.", ar: "الملف كنص." },
  tabNotesBody: { en: "Notes on this file.", ar: "ملاحظات على الملف ده." },
  fileViews: { en: "Views of this file", ar: "عرض الملف" },

  // Progress
  progressLabel: {
    en: "ONE is getting ready: downloading the search model",
    ar: "ONE بيجهز نفسه: بينزّل نموذج البحث",
  },
  downloaded: { en: "{done} of {total} MB", ar: "{done} من {total} ميجا" },
  progressWaiting: {
    en: "Waiting for the internet connection",
    ar: "مستني الاتصال بالإنترنت",
  },

  // StageBar and stages
  stageLabel: { en: "Stage {step} of {total}: {name}", ar: "المرحلة {step} من {total}: {name}" },
  stageReading: { en: "Reading the documents", ar: "قراءة المستندات" },
  stageQueries: { en: "Queries", ar: "الاستفسارات" },
  stageTakeoff: { en: "Take-off", ar: "الحصر" },
  stageQuotes: { en: "Supplier quotes", ar: "عروض الموردين" },
  stagePricing: { en: "Pricing", ar: "التسعير" },
  stageReview: { en: "Review", ar: "المراجعة" },
  stageHandover: { en: "Approval and handover", ar: "الاعتماد والتسليم" },
  stateWaiting: { en: "Waiting for you", ar: "مستني منك" },
  statePending: { en: "Not started", ar: "لسه" },

  // Collapsible
  details: { en: "Details", ar: "التفاصيل" },
  detailsBody: {
    en: "Item 7/03 has no unit in the bill of quantities; the specification gives cubic metres.",
    ar: "بند 7/03 من غير وحدة في جدول الكميات؛ المواصفات بتقول متر مكعب.",
  },

  // Separator
  or: { en: "or", ar: "أو" },
  signInGoogle: { en: "Continue with Google", ar: "كمّل بحساب Google" },
  useKey: { en: "Use an API key", ar: "استخدم مفتاح API" },

  // ScrollArea
  logStep: { en: "Step {n}: read page {page}", ar: "خطوة {n}: قرأ صفحة {page}" },

  // Toasts
  showNotice: { en: "Show a notice", ar: "اعرض إشعار" },
  showUndo: { en: "Show a notice with undo", ar: "اعرض إشعار بتراجع" },
  noteSaved: { en: "Note saved", ar: "الملاحظة اتحفظت" },
  fileRemoved: { en: "File removed from the tender", ar: "الملف اتشال من التندر" },
  fileBack: { en: "File put back", ar: "الملف رجع" },

  // ListRow and section labels
  waitingForYou: { en: "Waiting for you", ar: "مستني منك" },
  stages: { en: "Stages", ar: "المراحل" },
  teamNow: { en: "The team now", ar: "الفريق الآن" },
  approvePlan: { en: "Approve the tender plan", ar: "الموافقة على خطة التندر" },
  workPaused: { en: "Work is paused for your reply", ar: "الشغل متوقف على ردك" },
  leadMeta: { en: "Waiting for your approval of the plan", ar: "مستني موافقتك على الخطة" },
  contracts: { en: "Contracts engineer", ar: "مهندس العقود" },
  contractsMeta: { en: "Reading the conditions of contract", ar: "بيقرأ شروط العقد" },
  reviewer: { en: "Review engineer", ar: "مهندس المراجعة" },
  reviewerMeta: { en: "Waiting for the first output", ar: "مستني أول مخرج" },
  tenderOne: { en: "Office building, New Cairo", ar: "مبنى إداري، القاهرة الجديدة" },
  tenderOneMeta: { en: "Review, the review engineer is working", ar: "المراجعة، مهندس المراجعة شغال" },
  tenderTwo: { en: "School, 10th of Ramadan", ar: "مدرسة، العاشر من رمضان" },
  sectionModels: { en: "Models", ar: "الموديلات" },
  sectionAccount: { en: "Account", ar: "الحساب" },
  recommended: { en: "The recommended choice", ar: "الاختيار الموصى به" },
  recommendedMeta: {
    en: "ONE picks the strongest for the Lead and review, and the cheapest for quick questions",
    ar: "ONE يختار الأقوى للـ Lead والمراجعة والأرخص للأسئلة السريعة",
  },
  ownChoice: { en: "I choose a model for each role", ar: "أختار موديل لكل دور بنفسي" },
  onDevice: { en: "On this device only", ar: "على الجهاز فقط" },
  onDeviceMeta: { en: "Nothing leaves this computer", ar: "مفيش حاجة تخرج من الجهاز ده" },
});
