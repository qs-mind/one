// Words of the team room and the identity card (ui/src/team): the room's messages and message box, the team list,
// and a member's card.
import { defineTexts } from "./types";

export const team = defineTexts({
  // The room
  roomTitle: { en: "Team room", ar: "غرفة الفريق" },
  roomLabel: { en: "The team's conversation", ar: "محادثة الفريق" },
  roomEmpty: { en: "No messages yet", ar: "لسه مفيش رسايل" },
  roomEmptyBody: {
    en: "The team writes here while it works. You can write to them too.",
    ar: "الفريق بيكتب هنا وهو شغّال. وتقدر تكتبلهم إنت كمان.",
  },
  roomFailed: { en: "The team room did not open.", ar: "غرفة الفريق مافتحتش." },
  tryAgain: { en: "Try again", ar: "حاول تاني" },
  older: { en: "Earlier messages", ar: "رسايل أقدم" },
  you: { en: "You", ar: "إنت" },
  everyone: { en: "The team", ar: "الفريق" },
  unknownMember: { en: "A member not in this tender", ar: "عضو مش في التندر ده" },
  fromTo: { en: "{from} to {to}", ar: "{from} لـ {to}" },
  raised: { en: "{name} raised this to you", ar: "{name} طلّع ده للمهندس" },
  answered: { en: "{name} raised this to you. You answered.", ar: "{name} طلّع ده للمهندس، ورديت عليه." },
  answer: { en: "Answer in the conversation", ar: "رد في المحادثة" },

  // The room's message box
  messageLabel: { en: "Message to the team", ar: "رسالة للفريق" },
  placeholder: {
    en: "Write to the team; the Lead QS takes your words and steers them",
    ar: "اكتب للفريق؛ الـ Lead QS هياخد كلامك ويوجههم",
  },
  notSent: { en: "Not sent. Try again.", ar: "متبعتتش. حاول تاني." },

  // The team list
  teamTitle: { en: "The team", ar: "الفريق" },
  fixed: { en: "Fixed", ar: "ثابت" },
  permanent: { en: "Permanent", ar: "دائم" },
  temporary: { en: "Temporary, for this tender", ar: "مؤقت لهذا التندر" },
  independent: { en: "Independent of the team", ar: "مستقل عن الفريق" },
  proposed: { en: "Proposed with the plan", ar: "مقترح مع الخطة" },
  working: { en: "Working", ar: "شغّال" },
  failed: { en: "Its last work failed", ar: "آخر شغل ليه ماكملش" },
  firstTender: { en: "First tender with you", ar: "أول تندر له معك" },
  workedWith: {
    en: { one: "Worked with you on {n} tender", other: "Worked with you on {n} tenders" },
    ar: {
      zero: "لسه ماشتغلش معك في أي تندر",
      one: "اشتغل معك في تندر واحد",
      two: "اشتغل معك في تندرين",
      few: "اشتغل معك في {n} تندرات",
      many: "اشتغل معك في {n} تندر",
      other: "اشتغل معك في {n} تندر",
    },
  },
  specialityLine: { en: "Speciality: {value}", ar: "التخصص: {value}" },
  styleLine: { en: "Style: {value}", ar: "الأسلوب: {value}" },
  toolsLine: { en: "Tools: {value}", ar: "الأدوات: {value}" },
  recordLine: { en: "Record: {value}", ar: "السجل: {value}" },
  openCard: { en: "Open the card", ar: "افتح البطاقة" },

  // The identity card
  cardLabel: { en: "Identity card", ar: "بطاقة التعريف" },
  speciality: { en: "Speciality", ar: "التخصص" },
  style: { en: "Working style", ar: "الأسلوب" },
  tools: { en: "Tools", ar: "الأدوات" },
  model: { en: "Model", ar: "الموديل" },
  record: { en: "Record", ar: "السجل" },
  now: { en: "Now", ar: "دلوقتي" },
  modelBy: { en: "{name}, from {provider}", ar: "{name} من {provider}" },
  onDevice: { en: "Runs on this computer", ar: "بيشتغل على الجهاز ده" },
  offDevice: { en: "Runs outside this computer", ar: "بيشتغل برّه الجهاز ده" },
  noModel: { en: "No model can be used for it now", ar: "مفيش موديل ينفع يشتغل بيه دلوقتي" },
  noTools: { en: "No tools", ar: "مفيش أدوات" },
  checks: {
    en: "{passed} of {total} checked versions passed the Checking QS",
    ar: "{passed} من {total} نسخة اتراجعت عدّت من الـ Checking QS",
  },
  checksNone: { en: "None of its work was checked yet", ar: "لسه مفيش شغل ليه اتراجع" },
  cost: { en: "Paid AI cost so far: {cost}", ar: "تكلفة الذكاء الاصطناعي المدفوعة لحد دلوقتي: {cost}" },
  notInTender: { en: "This member is not in this tender.", ar: "العضو ده مش في التندر ده." },
  backToRoom: { en: "Back to the team room", ar: "ارجع لغرفة الفريق" },
  cardFailed: { en: "The card did not open.", ar: "البطاقة مافتحتش." },
});
