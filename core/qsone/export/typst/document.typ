// A Document as a PDF: A4, its blocks in order; each number reference carries a footnote with
// its source and date.
#import "common.typ": data, setup

#show: setup.with(size: 11pt)

#let run(r) = {
  text(
    weight: if r.at("b", default: false) { "bold" } else { "regular" },
    style: if r.at("i", default: false) { "italic" } else { "normal" },
    r.t,
  )
  if "note" in r { footnote(r.note) }
}

#let runs(rs) = { for r in rs { run(r) } }

#let blk(b) = {
  if b.k == "h1" { heading(level: 1, runs(b.runs)) }
  else if b.k == "h2" { heading(level: 2, runs(b.runs)) }
  else if b.k == "h3" { heading(level: 3, runs(b.runs)) }
  else if b.k == "quote" { quote(block: true, runs(b.runs)) }
  else if b.k == "list" {
    let items = b.items.map(item => { for x in item { blk(x) } })
    if b.ordered { enum(..items) } else { list(..items) }
  } else if b.k == "table" {
    table(
      columns: b.width,
      ..b.rows.map(row => row.map(cell => { for x in cell { blk(x) } })).flatten(),
    )
  } else { par(runs(b.runs)) }
}

#for b in data.blocks { blk(b) }
