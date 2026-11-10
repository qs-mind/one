//! Single-line TEXT, ATTRIB and ATTDEF values. They are not MTEXT: a backslash and a brace are
//! letters (`c\c`, `X:\Projects`, and `{` is ج in keyboard-mapped Arabic SHX fonts). Only the
//! percent codes and `\U+XXXX` escapes are decoded; `%%u`, `%%o` and `%%k` only switch a line
//! on or off and are dropped. Also the helpers that put a text on its row.

use acadrust::entities::mtext_format::parse_mtext;
use acadrust::CadDocument;
use serde_json::{json, Value};

pub fn plain(value: &str) -> String {
    let chars: Vec<char> = value.chars().collect();
    let mut out = String::new();
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == '%' && chars.get(i + 1) == Some(&'%') && i + 2 < chars.len() {
            let code = chars[i + 2].to_ascii_lowercase();
            let symbol = match code {
                'c' => Some(Some('Ø')),
                'd' => Some(Some('°')),
                'p' => Some(Some('±')),
                'u' | 'o' | 'k' => Some(None),
                _ => None,
            };
            if let Some(symbol) = symbol {
                out.extend(symbol);
                i += 3;
                continue;
            }
            let digits: String = chars[i + 2..(i + 5).min(chars.len())].iter().collect();
            if digits.len() == 3 && digits.chars().all(|c| c.is_ascii_digit()) {
                if let Some(c) = digits.parse::<u32>().ok().and_then(char::from_u32) {
                    out.push(c);
                    i += 5;
                    continue;
                }
            }
        }
        if chars[i] == '\\'
            && matches!(chars.get(i + 1), Some('U') | Some('u'))
            && chars.get(i + 2) == Some(&'+')
            && i + 7 <= chars.len()
        {
            let hex: String = chars[i + 3..i + 7].iter().collect();
            if let Some(c) = u32::from_str_radix(&hex, 16).ok().and_then(char::from_u32) {
                out.push(c);
                i += 7;
                continue;
            }
        }
        out.push(chars[i]);
        i += 1;
    }
    out
}

pub fn mtext(value: &str) -> String {
    parse_mtext(value, true)
        .to_plain_text()
        .chars()
        .take(8192)
        .collect()
}

pub fn single(value: &str) -> String {
    plain(value).chars().take(8192).collect()
}

pub fn raw(value: &str) -> String {
    value.chars().take(8192).collect()
}

pub fn text_style(doc: &CadDocument, name: &str, row: &mut Value) {
    row["style"] = json!(name);
    if let Some(style) = doc.text_styles.get(name) {
        row["font_file"] = json!(style.font_file);
        row["big_font_file"] = json!(style.big_font_file);
    }
}

pub fn long(out: &mut Value, value: &str) {
    if value.chars().count() > 8192 {
        out["limited"] = json!(true);
    }
}

pub fn place(row: &mut Value, x: f64, y: f64) {
    row["x"] = json!(x);
    row["y"] = json!(y);
}

#[cfg(test)]
mod tests {
    use super::plain;

    #[test]
    fn single_line_text_keeps_backslashes_and_braces() {
        assert_eq!(plain("5%%c12 @ 200 c\\c"), "5Ø12 @ 200 c\\c");
        assert_eq!(plain("S\\S sink - W\\C"), "S\\S sink - W\\C");
        assert_eq!(
            plain("X:\\Projects\\Hospital\\A-101"),
            "X:\\Projects\\Hospital\\A-101"
        );
        assert_eq!(plain("\\U+0645\\U+0637\\U+0628\\U+062E"), "مطبخ");
        assert_eq!(plain("%%uقطر%%u %%p0.5 %%d45 %%037"), "قطر ±0.5 °45 %");
        // keyboard-mapped Arabic SHX: "{" is a letter (ج) and must reach Python unchanged
        assert_eq!(plain("{hl,"), "{hl,");
        assert_eq!(plain("a}b{"), "a}b{");
    }
}
