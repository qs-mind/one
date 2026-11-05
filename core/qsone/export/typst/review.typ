// A Review report as a PDF: the Revision, the checks, the changes, and each comment thread with
// its replies and final status.
#import "common.typ": data, setup, slate

#show: setup.with(size: 10pt)

#text(size: 15pt, weight: "bold", data.title)

#for line in data.lines [ #line \ ]

== #data.checks_title
#for check in data.checks [
  - #strong(check.head)#if check.summary != "" [ \ #check.summary]
]

#data.changes

== #data.comments_title
#for thread in data.threads {
  block(breakable: false, above: 1em, {
    text(size: 9pt, fill: slate, thread.head)
    linebreak()
    thread.body
    for reply in thread.replies {
      // a reply sits one step in from the start side (right in Arabic)
      grid(columns: (1.5em, 1fr), inset: (y: 0.2em), [], {
        text(size: 9pt, fill: slate, reply.head)
        linebreak()
        reply.body
      })
    }
  })
}
