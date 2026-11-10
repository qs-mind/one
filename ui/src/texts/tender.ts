// Words of the tender place (ui/src/tender): its header, the side column, the plan that is not written yet, the
// document beside the conversation, and a number's source under a sheet.
import { defineTexts } from "./types";

export const tender = defineTexts({
  // The place and its header
  opening: { en: "Opening the tender", ar: "بيفتح التندر" },
  notOpened: { en: "This tender could not be opened.", ar: "التندر ده ماتفتحش." },
  submission: { en: "Submission {date}", ar: "التسليم {date}" },
  noSubmission: { en: "No submission date yet", ar: "لسه مفيش تاريخ تسليم" },
  submissionPassed: { en: "The submission day has passed", ar: "يوم التسليم فات" },
  submissionYours: { en: "The date you gave", ar: "التاريخ اللي إنت إديته" },
  submissionUnsure: { en: "Read by OCR and not sure: check it", ar: "قراءة ضوئية مش أكيدة: راجعها" },
  confidential: { en: "Confidential", ar: "سرّي" },
  archived: { en: "This tender is archived. Nothing more can be sent here.", ar: "التندر ده متأرشف. مفيش حاجة تتبعت هنا تاني." },
  failed: { en: "That did not go through. Try again.", ar: "ماتمّش. جرّب تاني." },

  // The side column
  sideLabel: { en: "Tender status", ar: "حالة التندر" },
  waitingTitle: { en: "Waiting for you", ar: "مستني منك" },
  nothingWaits: { en: "Nothing waits for you", ar: "مفيش حاجة مستنياك" },
  blocking: { en: "Work stops until you answer", ar: "الشغل متوقف على ردك" },
  stagesTitle: { en: "Stages", ar: "المراحل" },
  stageSignOff: { en: "Your sign-off", ar: "مستني اعتمادك" },
  stagesLabel: { en: "Stage {step} of {total}: {title}", ar: "المرحلة {step} من {total}: {title}" },
  teamTitle: { en: "The team now", ar: "الفريق الآن" },
  openRoom: { en: "Open the team room", ar: "افتح غرفة الفريق" },
  temporary: { en: "Temporary for this tender", ar: "مؤقت لهذا التندر" },
  proposed: { en: "Proposed with the plan", ar: "مقترح مع الخطة" },
  working: { en: "Working", ar: "شغّال" },
  waiting: { en: "Waiting", ar: "مستني" },
  idle: { en: "Nothing to do now", ar: "مفيش شغل دلوقتي" },
  documentsTitle: { en: "Documents", ar: "المستندات" },
  memberFailed: { en: "Its last work did not finish", ar: "آخر شغل ليه ماخلصش" },

  // No plan yet
  noPlanTitle: { en: "No plan yet", ar: "لسه مفيش خطة" },
  noPlanBody: {
    en: "The Lead QS writes the tender plan from the documents and the submission date. You approve it before any paid work starts.",
    ar: "الـ Lead QS بيكتب خطة التندر من المستندات وتاريخ التسليم. إنت بتوافق عليها قبل ما يبدأ أي شغل مدفوع.",
  },
  askForPlan: { en: "Ask the Lead QS to write the plan", ar: "اطلب من الـ Lead QS يكتب الخطة" },
  planAsked: { en: "The Lead QS is writing the plan", ar: "الـ Lead QS بيكتب الخطة" },

  // The document beside the conversation
  documentLabel: { en: "Open document", ar: "المستند المفتوح" },
  fullScreen: { en: "Full screen", ar: "ملء الشاشة" },
  closeDocument: { en: "Close the document", ar: "إغلاق المستند" },
  resize: { en: "Width of the conversation and the document", ar: "عرض المحادثة والمستند" },
  projectMap: { en: "Project Map", ar: "خريطة المشروع" },
  projectFiles: { en: "Project files", ar: "ملفات المشروع" },
  documentTitle: { en: "Document", ar: "مستند" },
  fileTitle: { en: "File", ar: "ملف" },
  noDocument: { en: "This document cannot be opened here.", ar: "المستند ده مش بيتفتح هنا." },

  // A number's source, under the sheet
  sourceLabel: { en: "Where the number comes from", ar: "مصدر الرقم" },
  sourceReading: { en: "Reading where it comes from", ar: "بيقرأ مصدره" },
  sourceNone: { en: "This number has no source yet.", ar: "الرقم ده لسه مالوش مصدر." },
  sourceFailed: { en: "Its source could not be read.", ar: "مصدره ماتقريش." },
  sourceMade: { en: "Worked out: {formula}", ar: "محسوب: {formula}" },
  sourceFrom: { en: "Source: {title}", ar: "المصدر: {title}" },
  sourceStale: { en: "Its inputs changed since: work it out again", ar: "مدخلاته اتغيرت من ساعتها: يتحسب تاني" },
  openSource: { en: "Open the source", ar: "افتح المصدر" },
  closeSource: { en: "Close the source", ar: "اقفل المصدر" },
});
