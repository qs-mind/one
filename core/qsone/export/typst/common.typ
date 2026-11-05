// Shared by every PDF export. Every value arrives as text in `sys.inputs.data` (JSON) and is
// placed as text: nothing here reads content as markup, and nothing computes a number.
#let data = json(bytes(sys.inputs.data))

#let ink = rgb("#0E0F12")
#let stone = rgb("#F2EEE7")
#let paper = rgb("#F9F8F4")
#let slate = rgb("#6E6A64")
#let copper = rgb("#A6491B")

// The page: the marks on every page (draft, sample data), and a footer with the title, the
// Revision or the draft mark, and page x of y.
#let setup(body, flipped: false, size: 10pt) = {
  set document(title: data.title)
  // Kerning off: with it, pdfium reads a gap inside some Arabic words as a space.
  set text(
    font: data.fonts, lang: data.lang, dir: if data.dir == "rtl" { rtl } else { ltr },
    size: size, fill: ink, kerning: false,
  )
  set page(
    paper: "a4",
    flipped: flipped,
    margin: (x: 1.4cm, top: 1.8cm, bottom: 1.6cm),
    header: if data.marks.len() > 0 {
      align(center, text(size: 9pt, weight: "bold", fill: copper, data.marks.join(" · ")))
    },
    footer: context text(size: 8pt, fill: slate, grid(
      columns: (1fr, auto, 1fr),
      align(start, data.title),
      data.state,
      align(end, data.page_of
        .replace("{x}", str(counter(page).get().first()))
        .replace("{y}", str(counter(page).final().first()))),
    )),
  )
  set table(stroke: 0.4pt + slate.lighten(60%), inset: 4pt)
  show heading: set text(fill: ink)
  body
}
