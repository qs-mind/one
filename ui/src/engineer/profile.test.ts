import { describe, expect, it } from "vitest";
import { engineer } from "@/texts/engineer";
import { currencyChoices, formOf, problemText, profileSchema, toProfileIn, type ProfileForm } from "./profile";

const filled: ProfileForm = {
  first_name: "مهندس",
  last_name: "تجريبي",
  position: "مدير المكتب الفني",
  company: "شركة مقاولات",
  org_type: "contractor",
  country: "EG",
  currency: "EGP",
};
const problems = (form: ProfileForm) => {
  const result = profileSchema.safeParse(form);
  return result.success ? {} : Object.fromEntries(result.error.issues.map((issue) => [issue.path[0], issue.message]));
};

describe("the profile schema", () => {
  it("passes the seven fields filled", () => {
    expect(problems(filled)).toEqual({});
  });

  it("stops at any empty field, a blank one too", () => {
    const empty = formOf({ first_name: "", last_name: "", position: "", company: "", org_type: null, country: null, currency: null, complete: false });
    expect(Object.keys(problems(empty)).sort()).toEqual(["company", "country", "currency", "first_name", "last_name", "org_type", "position"]);
    expect(problems({ ...filled, company: "   " })).toEqual({ company: "missing" });
  });

  it("holds the core's bounds: names of 80, a position or company of 120, a currency of three capitals", () => {
    expect(problems({ ...filled, first_name: "م".repeat(81) })).toEqual({ first_name: "tooLong:80" });
    expect(problems({ ...filled, position: "م".repeat(120) })).toEqual({});
    expect(problems({ ...filled, company: "م".repeat(121) })).toEqual({ company: "tooLong:120" });
    expect(problems({ ...filled, currency: "egp" })).toEqual({ currency: "currency" });
    expect(problems({ ...filled, org_type: "supplier" })).toEqual({ org_type: "choose" });
  });

  it("says each problem in words", () => {
    expect(problemText("first_name", "missing")).toEqual({ pair: engineer.missingText });
    expect(problemText("country", "choose")).toEqual({ pair: engineer.missingChoice });
    expect(problemText("company", "tooLong:120")).toEqual({ pair: engineer.tooLong, max: 120 });
  });

  it("sends a half-filled form with empty choices as null", () => {
    expect(toProfileIn({ ...filled, org_type: "", country: "", currency: "" })).toEqual({
      ...filled,
      org_type: null,
      country: null,
      currency: null,
    });
  });

  it("offers every currency, the usual three first, named in the page's language", () => {
    const choices = currencyChoices("ar-u-nu-latn");
    expect(choices.slice(0, 3).map((c) => c.value)).toEqual(["EGP", "SAR", "AED"]);
    expect(choices.length).toBeGreaterThan(100);
    expect(choices[0]!.label).toMatch(/جنيه.*\(EGP\)/);
  });
});
