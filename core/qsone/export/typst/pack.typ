#import "common.typ": ink, copper, paper
#let d = json(bytes(sys.inputs.data))
#set page(width: d.width * 1pt, height: d.height * 1pt, margin: 18pt, fill: if d.large { paper } else { none })
#set text(font: ("Zain", "Kumbh Sans"), lang: d.lang,
  dir: if d.lang == "ar" { rtl } else { ltr }, kerning: false,
  size: if d.large { 24pt } else { 12pt }, fill: if d.large { ink } else { copper })
#let pos = if d.position == "top" { top } else if d.position == "bottom" { bottom } else { horizon }
#place(pos + center, block(width: 100%, align(center, d.text)))
