// The design gallery's own words (dev only, served at /fake.html), its state names, and the foundation samples.
import { defineTexts } from "../types";

export const foundation = defineTexts({
  title: { en: "ONE design system", ar: "نظام تصميم ONE" },
  intro: {
    en: "Every component, in every state, in both languages and both themes. For development only.",
    ar: "كل مكون بكل حالاته، باللغتين وفي المظهرين. للتطوير بس.",
  },
  switches: { en: "Gallery switches", ar: "مفاتيح المعرض" },

  // The three switches at the top
  page: { en: "Page", ar: "الصفحة" },
  viewGallery: { en: "Gallery", ar: "المعرض" },
  viewSpecimens: { en: "Specimens", ar: "النماذج" },
  language: { en: "Language", ar: "اللغة" },
  arabic: { en: "Arabic", ar: "العربية" },
  english: { en: "English", ar: "الإنجليزية" },
  theme: { en: "Theme", ar: "المظهر" },
  themeSystem: { en: "System", ar: "النظام" },
  themeLight: { en: "Light", ar: "فاتح" },
  themeDark: { en: "Dark", ar: "داكن" },

  // Sections of the gallery
  sectionFoundation: { en: "Foundation", ar: "الأساس" },
  sectionControls: { en: "Controls", ar: "عناصر التحكم" },
  sectionSurfaces: { en: "Surfaces", ar: "الأسطح" },

  // State names shown over each sample
  rest: { en: "At rest", ar: "عادي" },
  hover: { en: "Hover", ar: "تحت المؤشر" },
  pressed: { en: "Pressed", ar: "مضغوط" },
  focus: { en: "Focus", ar: "تركيز" },
  disabled: { en: "Disabled", ar: "معطّل" },
  loading: { en: "Loading", ar: "جاري التحميل" },
  error: { en: "Error", ar: "خطأ" },
  checked: { en: "Checked", ar: "متعلّم عليه" },
  armed: { en: "Armed", ar: "جاهز للتأكيد" },
  current: { en: "Current", ar: "الحالي" },
  filled: { en: "With text", ar: "فيه كلام" },
  wraps: { en: "Wraps at 280px", ar: "بيلف على 280px" },
  opensOnClick: { en: "Opens on a click", ar: "بيفتح بالضغط" },
  open: { en: "Open", ar: "مفتوح" },

  // Foundation samples
  valueHere: { en: "In this theme", ar: "في المظهر ده" },
  typeSample: { en: "Concrete for the ground beams", ar: "خرسانة الميدات" },
  files: { en: "{n} files", ar: "{n} ملف" },
  mirrors: { en: "Turns with the reading direction", ar: "بيتقلب مع اتجاه القراءة" },
  neverMirrors: { en: "Never turns", ar: "عمره ما بيتقلب" },
  dense: { en: "Dense: inside a data sheet only", ar: "كثيف: جوه جدول بيانات بس" },
  roomy: { en: "Roomy: everywhere else", ar: "مريح: في أي مكان تاني" },
  sheetLabel: { en: "Concrete works, sample", ar: "أعمال الخرسانة، عينة" },
  colItem: { en: "Item", ar: "البند" },
  colDescription: { en: "Description", ar: "الوصف" },
  colQuantity: { en: "Quantity (m³)", ar: "الكمية (م³)" },
  rowPlain: { en: "Plain concrete for footings", ar: "خرسانة عادية للقواعد" },
  rowFootings: { en: "Reinforced concrete for footings", ar: "خرسانة مسلحة للقواعد" },
  rowBeams: { en: "Reinforced concrete for ground beams", ar: "خرسانة مسلحة للميدات" },
  total: { en: "Total", ar: "الإجمالي" },
  cubicMetre: { en: "m³", ar: "م³" },
  submission: { en: "Submission {date}", ar: "التسليم {date}" },
});
