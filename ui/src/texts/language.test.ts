import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { dirOf, getLang, setLang, textDir, useLang } from "./language";
import { useText } from "./useText";
import { common } from "./common";

afterEach(() => setLang("ar"));

describe("language store", () => {
  it("puts lang and dir on <html> and tells subscribers", () => {
    const { result } = renderHook(() => useLang());
    act(() => setLang("en"));
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
    expect(result.current).toMatchObject({ lang: "en", dir: "ltr" });
    act(() => setLang("ar"));
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(result.current).toMatchObject({ lang: "ar", dir: "rtl" });
    expect(getLang()).toBe("ar");
  });

  it("re-renders useText in the new language", () => {
    const { result } = renderHook(() => useText());
    act(() => setLang("ar"));
    expect(result.current(common.close)).toBe("إغلاق");
    act(() => setLang("en"));
    expect(result.current(common.close)).toBe("Close");
    expect(result.current.lang).toBe("en");
  });

  it("keeps nothing in web storage or cookies", () => {
    const storage = [
      vi.spyOn(Storage.prototype, "setItem"),
      vi.spyOn(Storage.prototype, "getItem"),
      vi.spyOn(Storage.prototype, "removeItem"),
    ];
    const cookieGet = vi.spyOn(Document.prototype, "cookie", "get");
    const cookieSet = vi.spyOn(Document.prototype, "cookie", "set");
    const { result } = renderHook(() => useLang());
    act(() => setLang("en"));
    act(() => result.current.setLang("ar"));
    for (const spy of [...storage, cookieGet, cookieSet]) expect(spy).not.toHaveBeenCalled();
  });

  it("gives the direction of a language and of data text", () => {
    expect(dirOf("ar")).toBe("rtl");
    expect(dirOf("en")).toBe("ltr");
    expect(textDir("Lead QS طلّع ده")).toBe("rtl");
    expect(textDir("Lead QS")).toBe("ltr");
    expect(textDir("")).toBe("ltr");
  });
});
