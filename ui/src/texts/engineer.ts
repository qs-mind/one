// The engineer's profile: its seven fields, their choices and what is wrong with a value. First launch (step 2) and
// Settings, My profile, both show them.
import { defineTexts } from "./types";

export const engineer = defineTexts({
  first_name: { en: "First name", ar: "الاسم الأول" },
  last_name: { en: "Last name", ar: "الاسم الأخير" },
  position: { en: "Position", ar: "المنصب" },
  positionExample: { en: "Example: senior pricing engineer", ar: "مثال: مهندس تسعير أول" },
  company: { en: "Company", ar: "الشركة" },
  org_type: { en: "Type of organisation", ar: "نوع الجهة" },
  contractor: { en: "Contractor", ar: "مقاول" },
  consultant: { en: "Consultant", ar: "استشاري" },
  owner: { en: "Owner", ar: "مالك" },
  procurement: { en: "Procurement", ar: "توريد" },
  country: { en: "Country", ar: "البلد" },
  EG: { en: "Egypt", ar: "مصر" },
  SA: { en: "Saudi Arabia", ar: "السعودية" },
  AE: { en: "United Arab Emirates", ar: "الإمارات" },
  other: { en: "Another country", ar: "بلد تاني" },
  currency: { en: "Currency", ar: "العملة" },
  choose: { en: "Choose", ar: "اختار" },
  missingText: { en: "Write this in.", ar: "اكتب ده." },
  missingChoice: { en: "Choose one.", ar: "اختار واحد." },
  tooLong: { en: "Write {max} characters at most.", ar: "اكتب {max} حرف بالكتير." },
  badCurrency: { en: "Choose a currency from the list.", ar: "اختار عملة من القايمة." },
  kept: {
    en: "Your details are kept encrypted on this computer. You can change them any time.",
    ar: "بياناتك محفوظة مشفرة على جهازك. تقدر تعدلها أي وقت.",
  },
  notSaved: { en: "Not saved yet. ONE tries again as you type.", ar: "لسه متحفظش. ONE هيحاول تاني وإنت بتكتب." },
});
