# Check mode — auditing a deck before it goes out

Two halves. Run the machine half first; it is fast and it is never wrong about
what it claims. Then do the reading half, which is the one that matters.

```bash
python3 dfns_slide.py audit deck.txt     # or  - for stdin
```

Extract the deck's visible text first — one line per text element, in reading
order, so the line numbers mean something.

---

## What the audit settles, so you don't have to

Terminology (`on-chain`, `rules engine`, `approval workflow`, `key custody`),
padding words, buzzwords, hedging, exclamation marks, emoji, `DFNS` casing,
bare superlatives, and any figure that `facts.json` cannot vouch for.

It already knows two things people get wrong when they do this by hand:

- **Technical identifiers are not casing errors.** `api.dfns.io`, `@dfns/sdk`,
  `DfnsApiClient`, `X-Dfns-Signature` are correct as written. The audit exempts
  them. A previous manual review flagged eleven such occurrences as faults and
  every one was correct.
- **Third-party quotes are never rewritten.** Banned words inside a customer or
  press quote belong to the speaker. The audit reports them under `QUOTED` as
  context, and they are not counted as faults. Do not "fix" them.

---

## What only a reader can settle

### 1. Is the title two beats, or one flat clause?

The most common way a DFNS slide goes off-brand while every token is correct.

```
✗  Our platform provides secure and scalable wallet infrastructure
✓  Trust nothing. Verify everything.  │  Us too.
```

Look for: a single clause; a title that describes rather than claims; a second
beat that merely continues the first instead of landing it.

### 2. Does every claim carry its evidence?

Not "is there a number" — the audit does that. The question is whether a reader
who doubts this sentence has anything to check.

- A superlative with no source named **in the same breath** → cut it or source it.
  `#1 wallet infrastructure` works when G2 is next to it and fails when it is not.
- An internal benchmark presented as neutral → label it:
  *"Internal benchmark, verify before external use."*
- A figure with no date where the date changes its meaning.

### 3. Is it selling fear?

Describe the mechanism and the fear answers itself.

```
✗  Your assets are at risk without proper key management
✓  Key material is born sharded and stays sharded
```

### 4. One slide, one idea

If you can't say what the slide argues in a sentence, it is two slides. Symptoms:
a title that uses "and" to join unrelated halves; more than five items; a body
that introduces a second audience.

### 5. Form

- Dual-tone title flattened to one colour → broken.
- Any heading in Medium or Semibold → headings are Light 300.
- A figure set in Inter rather than Roboto Mono → it reads as someone else's deck.
- A colour that is not in `tokens.json` → there is no such thing as an
  approximately-brand purple.
- An outline icon → solid only.

### 6. Is the deck still true?

Every figure carries a date in `facts.json`. A deck built in March and presented
in September may be accurate and stale at once. Check the `facts v…` stamp in the
footer against today.

---

## Reporting

Order findings by what they cost, not by how many there are:

1. **Factual** — a figure that is wrong, or that contradicts `facts.json`
2. **Claim** — a superlative or assertion with nothing behind it
3. **Terminology** — the words we have decided on
4. **Style** — padding, hedging, punctuation
5. **Form** — colour, weight, icon family

For each: quote the line, say what is wrong in one sentence, give the fix. Do not
rewrite the deck unasked.

And say plainly when a deck is clean. A check that always finds something stops
being read.
