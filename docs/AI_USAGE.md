## Candidate's review

The coding agent wrote nearly all of the code. The design decisions, trade-offs and judgment calls
are mine, and `docs/DECISIONS.md` records them.

**Decided by me**
- Plain Python orchestration with a Postgres-backed queue, rather than LangGraph or CrewAI (§1).
- The "model proposes, rules can only make it safer" split, including the one-way override rule (§2).
- Using retrieval as a second classifier, and choosing the margin (0.04) and `RETRIEVAL_MIN_SCORE`
  (0.55) by looking at the visible tickets' scores. I flagged in the doc that these are tuned to the
  visible data (§3).
- Combining a structural injection scorer with the model flag instead of a keyword list, and writing
  the probe set myself. I widened the detector after the first measurement, so the probes are no
  longer held out (§4).
- Exactly-once behaviour through database constraints and same-transaction lease completion rather
  than application-level checks (§5, §6), and the hashed-shingle approach to keeping other tenants'
  content away from the checker (§7).
- No automatic holding reply on escalations (§8), and the scaling plan for 50 tenants (§9).
- Where I disagree with the brief or the golden labels (HD-T04, HD-T12, NW-T08). I kept the rules as
  written and recorded the disagreements instead of tuning the system to match single labels.

**Reviewed and caught by me**
- I read every draft in full instead of trusting the approval-queue summary. That is how the empty
  `kb_refs`, the mixed-up HD-T06 draft and the sales-lead misrouting (NW-T12) were found.
- I printed the retrieval scores and found that `RETRIEVAL_MIN_SCORE` couldn't separate covered from
  uncovered requests.

**Written by hand**
- `eval/NOTES.md`.

**What I can explain and defend:** every decision in DECISIONS.md, including its costs and the
alternatives I rejected.