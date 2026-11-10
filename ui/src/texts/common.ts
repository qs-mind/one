// Words every part of the new interface shares. Groups A and B read this file; they never edit it.
import { defineTexts } from "./types";

export const common = defineTexts({
  close: { en: "Close", ar: "إغلاق" },
  send: { en: "Send", ar: "إرسال" },
  undo: { en: "Undo", ar: "تراجع" },
  sample: { en: "Sample data", ar: "بيانات عينة" },
  navigation: { en: "Navigation", ar: "التنقل" },
  home: { en: "Home", ar: "الرئيسية" },
  tenders: { en: "Tenders", ar: "التندرات" },
  settings: { en: "Settings", ar: "الإعدادات" },
  notifications: { en: "Notices", ar: "الإشعارات" },
  done: { en: "Done", ar: "تمت" },
  now: { en: "Now", ar: "الآن" },
  loading: { en: "Loading", ar: "جاري التحميل" },
  dropHere: { en: "Drop files here", ar: "أفلت الملفات هنا" },
  holdToConfirm: { en: "Press and hold to go ahead", ar: "اضغط واستمر للتأكيد" },
  holdHelpReader: {
    en: "Press and hold, or press twice with a screen reader",
    ar: "اضغط واستمر، أو اضغط مرتين مع قارئ الشاشة",
  },
  pressAgain: { en: "Press again to confirm", ar: "اضغط مرة تانية للتأكيد" },
  stepOf: { en: "Step {step} of {total}", ar: "الخطوة {step} من {total}" },
  daysLeft: {
    en: { one: "{n} day left", other: "{n} days left" },
    ar: {
      zero: "لا أيام باقية",
      one: "باقي يوم",
      two: "باقي يومين",
      few: "باقي {n} أيام",
      many: "باقي {n} يوم",
      other: "باقي {n} يوم",
    },
  },
});
