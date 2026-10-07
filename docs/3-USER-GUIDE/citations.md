# Citations - Verify AI Answers

Every claim the research agent makes from your notebook is followed by a citation to the most specific place it
read: usually a page or page range. Citations are how you check an answer against the source.

---

## What a citation points to

The agent cites **addresses** it actually read (it's told never to invent one):

| In the answer | Shown as | Points to |
|---|---|---|
| `[source:abc#p94]` | p. 94 | one page of a PDF source |
| `[source:abc#p86-93]` | pp. 86–93 | a page range |
| `[source:abc#s3]` | section 3 | a topic section of the document's outline |
| `[source:abc/summary]` | summary | the document summary |
| `[source:abc#c12]` | #12 | a chunk of a non-PDF source (web page, text, transcript) |
| `[note:xyz]` | the note | a note |
| `[source:abc]` | the source | the whole source (older answers, or when no finer address applies) |

Answers that use [web search](../5-CONFIGURATION/research-agent.md#web-search) cite web pages as ordinary links,
separate from notebook citations.

## Where you see them

- **In the answer**: numbered chips like **①**. Each distinct location gets its own number; repeated citations of
  the same page reuse it. **Hover** a chip to see the cited page, the document title and the page or section.
- **Under the answer**: **Sources**, a thumbnail of every cited page with its number, title and page.
- **Clicking a page citation** in notebook chat opens the page in the **evidence panel** beside the conversation,
  rendered from the original PDF and marked *Cited*. The arrows move through the whole document, the outline section
  it belongs to is shown, and for a range the cited pages are listed as thumbnails. **Open source** opens the whole
  source. In Ask and source chat the page opens in a preview dialog instead. Other citations open the source, note
  or insight in a dialog.

If the original file isn't stored, the preview says *This page can't be shown*; the citation still names the page.

---

## Checking a claim

1. Click the citation next to the claim and read the page.
2. If the page doesn't support it, ask a follow-up: "Where exactly does it say that? Quote the passage." The agent
   re-reads the cited pages.
3. **Researched in N steps** above the answer shows what the agent searched and read, which helps when a citation looks off.

The model chooses what to cite, so a citation can be missing or imprecise. In the course eval the agent cited the
right page for 30 of 30 answers, but treat citations as a pointer to check, not as proof.

---

## Keeping cited answers

**Save to note** (notebook chat) and **Save to Notebooks** (Ask) keep the answer text with its citations; they stay
clickable in the note. **Copy to clipboard** copies the answer text.
