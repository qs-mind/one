// A Sheet as a PDF: A4 landscape, the header row repeated on every page, then the sources of
// every number shown, one line each.
#import "common.typ": data, paper, setup, stone

#show: setup.with(flipped: true, size: 8.5pt)

#text(size: 13pt, weight: "bold", data.title)

#table(
  columns: data.columns.map(c => c.width * 1fr),
  table.header(..data.columns.map(c => table.cell(fill: stone, align: center + horizon, strong(c.label)))),
  ..data.rows.map(row => row.cells.map(c => table.cell(
    colspan: c.span,
    align: if c.num { end } else { start },
    fill: if row.kind == "item" { none } else { paper },
    if row.kind == "item" { c.t } else { strong(c.t) },
  ))).flatten(),
)

#if data.sources.len() > 0 {
  pagebreak()
  text(size: 11pt, weight: "bold", data.sources_title)
  // one line per number, not a table: a 2,000-row Sheet has 6,000 of them, and as table
  // cells Typst needs about 1 GB to lay them out
  set text(size: 7.5pt)
  set par(spacing: 0.55em)
  columns(2, for line in data.sources { par(line) })
}
