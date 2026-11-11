# Maintenance review — 2026-11-10

Status: open backlog and documentation audit, not an implementation or release.
Baseline: `f034d91ead146d2edfad5c0c32ba8d37464efd50` (main, 2.3.0rc7).

## Scope and evidence

Focused source review of persistence/playback, tournament scheduling/ranking/UI,
generation completion, updater, frontend transport, release workflows and documentation.
Inventory: all 50 Markdown paths on main (22 release notes); current document sections
and stale-scope statements inspected. status.md is a historical log, sampled rather
than treated as a current specification. This is not an exhaustive security or model audit.

Two isolated Python checks executed the production Store/Playback methods and
rank_clips function, with temporary SQLite storage and stub service dependencies.
Both behaviors below reproduced. No full pytest/browser suite, real inference,
Windows/OBS acceptance or live Twitch test was run for this documentation-only review.

## Prioritized fixes and design decisions

### B1 — P1: history pagination can hide pending playback (reproduced)

Evidence: `src/pacttsclone/playback.py`, Playback.items/tick/pause/panic;
`src/pacttsclone/store.py`, Store.channel_records (default limit 1000).

items() loads the 1000 most recently updated records, then sorts those by creation
time. The same truncated history drives queue execution and cancellation. Keep an
older item queued, then create/cancel 1000 later items: the old record remains
queued in SQLite but tick returns item=None. This is reachable while the channel
is paused and later items are repeatedly cancelled; it does not require a queue
containing 1000 simultaneous pending jobs.

Fix: query pending playback by channel/status directly, ordered by created_at with
a deterministic tie-breaker. Paginate display history separately. Use the pending
query for queue limits, ticking, pause and panic. Avoid replacing 1000 with a larger
magic number.

Acceptance: enqueue/cancel later records beyond the history limit; the original
item remains visible to execution, cancellation and capacity accounting.
Review the similar fixed 100000-row startup recovery scans separately.

### B2 — P2: ranking can make a universal loser the first “winner” (reproduced)

Evidence: `src/pacttsclone/tournaments.py`, rank_clips final sort and
TournamentStore._candidate_clips(period="winners").

The final key is (provisional, -score, clip). Confidence status dominates strength.
Input: A loses once to each of B/C/D/E/F. A has five comparisons and is
non-provisional; every opponent has one comparison and is provisional.
Observed result: A ranks first (score approximately 0.201), ahead of all five
winners (approximately 1.307 each). Previous Winners takes ranked[0].

Decision/fix: separate confidence display from winner eligibility. Either sort the
main ranking by strength with a provisional badge, or explicitly show separate
established/provisional groups and never infer a champion from the first row.
Specify tie/low-evidence policy before changing the algorithm.

Acceptance: the five-loss example cannot silently produce A as champion.

### B3 — P2: “Bracket” and “Previous Winners” lack tournament semantics (source-confirmed)

Evidence: `tournaments.py`, pair, bracket, _candidate_clips; `static/tournaments.js`.

pair() iterates unseen combinations, not elimination rounds. N entries can require
N*(N-1)/2 comparisons (100 clips = 4950), rather than N-1 elimination matches.
The bracket view displays comparison history. There is no completion/champion
field, yet Previous Winners takes current leaders from any tournament with counted
comparisons, including unfinished tournaments.

Choose explicitly: implement an elimination bracket with byes, rounds, advancement,
completion and a persisted champion; or label the current mode as pairwise ranking.
Keep public crowd voting separate from this choice. Persist original date range,
mode and frozen entrants so old tournaments are reproducible.

Acceptance: for five entries, verify byes and four decisive matches if elimination
is selected; unfinished tournaments cannot contribute a previous champion.
Twitch polls are currently advisory: there is no automatic poll-result-to-vote
advancement. Document that behavior rather than treating it as a confirmed failure.

### B4 — P1 candidate: diagnostic I/O can terminate the generation dispatcher (static)

Evidence: `service.py`, _dispatch, _execute finally, _log and log_generation_vram.

_dispatch calls _execute without an outer recovery boundary. Completion performs
log/file/resource operations in finally; _log writes generation.jsonl without an
I/O guard. A disk-full/permission error there can escape after completing a job,
kill the queue thread and prevent subsequent jobs from executing. Earlier failures
in the finally block can also leave active state uncleared.

Fix: guarantee active-state cleanup; isolate optional diagnostics from durable job
completion; expose a persistent service failure if SQLite itself is unavailable.
Do not swallow database failures and pretend the job succeeded.

Acceptance: fault-inject OSError separately into diagnostic logging, cleanup and
persistence; verify documented job state, dispatcher health and subsequent work.
Not reproduced in a full service process during this review.

### D1 — P2: enforce the release gate in automation

Evidence: `.github/workflows/release-merged.yml`, application job, and
`scripts/publish-release.ps1`.

The app-only publish job runs lint and updater tests; it does not itself check that
the normal core/browser checks passed for the intended release commit. The separate
push tests run independently. This is a workflow gap, not evidence that a bad build
was published. Repository branch protection was not verified.

Improve: verify reusable successful check evidence for the chosen commit, or use an
explicit workflow dependency. Preserve fast app-only releases; do not reintroduce
installer acceptance for every patch. Define how PR test evidence applies to the
merge commit, and reject pending/failed/mismatched evidence.

### D2 — P2: avoid coupling unrelated CI jobs

Evidence: `.github/workflows/tests.yml`, core.needs=[fast, windows-tools].
Linux core jobs wait for the Windows FFmpeg download job even though only Windows
uses its artifact. Separate the platform dependencies so a Windows tool download
does not delay or block Linux validation. Keep actual compatibility coverage.
The legacy migration-bridge job and publish-accepted-rc11 workflow also deserve a
one-time-workflow retirement review; remove only after checking recovery uses.

### D3 — P2: paginate the release catalogue

Evidence: `updater.py`, API ends in releases?per_page=100; check performs one fetch.
Older pinned versions eventually disappear from the selectable catalogue once
outside the first page. Add bounded pagination or direct tag lookup for a pinned
version, with existing size/hash/identity validation. This is a future scale limit,
not a claim that the repository already has over 100 releases.

### D4 — P2: translate the tournament UI consistently

Evidence: `static/tournaments.js` builds labels, errors, buttons, poll status and
ranking text as English literals, without the shared translation helper. The
app's localechange handler does not rerender those dynamic tournament strings.
Move user-facing text to the existing locale mechanism, preserve IDs/original
content, and test switching language after loading a tournament.

### D5 — P3: clearer ownership and persistence boundaries

TournamentStore directly accesses Store.db/lock and creates its schema at route
registration. Store.put commits independently; future mixed operations could
accidentally break larger transactions. Introduce explicit transaction ownership
and schema migration/versioning before expanding tournament state. Keep this
targeted; no framework rewrite is needed.

Keep the good existing decisions: native frontend modules, spawned/cancellable
inference, SQLite as authoritative state, bounded/coalesced SSE, verified update
assets and separation of installer changes from application patches.

## Documentation and agent context

**Keep historical release notes. Their existence does not by itself load them into
an agent's context. The problem is mandatory bulk reading and ambiguous authority.**

AGENTS.md is useful and only 952 bytes. There is no second agent.md in the audited
tree. However, it tells agents to read README, requirements, architecture,
decisions, testing, status and v2-design before behavior changes: **203525 bytes**
combined, before source code. Bytes are measured; this is not an exact token count.

Specific conflicts:

- AGENTS.md still calls the integration read-only IRC and v2-design the current scope.
- v2-design retains “no OAuth credentials” in its original section and describes an
  incoming Discord bot in its final section; current Discord integration is output-only webhooks.
- “An automatic updater is not implemented” persists in architecture, requirements,
  decisions, testing and known-issues despite updater.py and auto-updates.md.
- The same RC4 setup/organization/observability sections recur across requirements,
  architecture, decisions and testing.
- bug-handoff-sfx-obs.md opens with repairs unfinished/unmerged and rc.5 unreleased;
  main already includes rc.5 repair code/release notes. Keep genuine hardware/upload
  validation limitations, but clearly distinguish them from superseded branch status.
- Completed task plans require full installer releases; these are historical gates,
  not the current app-only release procedure.
- status.md is 64530 bytes and starts at v0.2. It is useful evidence, not a startup
  reading requirement.
- frontend.md's routing table omits sfx.js and tournaments.js.

### Recommended reading contract

1. Keep one small root AGENTS.md: commands, durable invariants and a task-to-doc map.
   Remove the blanket read-all requirement. Do not duplicate a second agent.md.
2. Read the relevant implementation/tests and one feature contract as needed.
3. Keep a short current backlog with severity, evidence, acceptance and resolution
   links. This review is a starting backlog; resolved items should become history.
4. Keep decisions as dated rationale with explicit superseded-by links. Do not
   repeat changelog paragraphs in requirements, architecture and testing.
5. Keep historical documents in place initially, with clear historical banners.
   Moving them is optional and requires updating inbound links and release scripts.
6. For docs-only changes, verify links/content; do not claim runtime coverage.
   Behavior changes still need the relevant tests and release gates.

This matches just-in-time context retrieval: maintain lightweight paths and load
relevant content when needed. Reference:
https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

### File-by-file disposition (all 50 Markdown files on main)

| File | Recommendation |
| --- | --- |
| AGENTS.md | Keep; replace mandatory bulk reading and stale scope with concise routing/invariants. |
| README.md | Keep user setup/usage; move release-specific narration into history and link feature guides. |
| docs/architecture.md | Keep a current system map; consolidate duplicated historical feature paragraphs. |
| docs/requirements.md | Keep current constraints; remove superseded exclusions after preserving their history. |
| docs/decisions.md | Keep rationale/history; mark superseded decisions and read only relevant sections. |
| docs/testing.md | Keep current commands and acceptance boundaries; separate dated test counts/results. |
| docs/status.md | Keep as historical evidence; remove from routine startup reading. |
| docs/known-issues.md | Refresh into an actual current backlog; retain the RC5 review as historical evidence. |
| docs/auto-updates.md | Keep as the current updater contract; link the release procedure when merged. |
| docs/discord.md | Keep as current webhook contract; use it to correct old bot descriptions. |
| docs/frontend.md | Keep module map; add SFX/tournament modules and remove refactor-only status prose. |
| docs/realtime-communication.md | Keep current SSE/access/recovery contract. |
| docs/twitch-eventsub.md | Keep feature-specific OAuth/event contract and validation limits. |
| docs/optional-imports.md | Keep migration and preservation contract. |
| docs/ming-integration.md | Keep current engine/runtime contract. |
| docs/ming-inference-diagnosis.md | Keep technical diagnosis; historical findings with current fix references. |
| docs/kitten-integration.md | Keep current engine/runtime contract. |
| docs/multi-voice-sfx.md | Keep current feature contract and real-world validation limits. |
| docs/bug-handoff-sfx-obs.md | Historical handoff; mark superseded status and extract only remaining investigations. |
| docs/installer-design.md | Historical RC4 design; retain rationale, route current work through actual installer and updater docs. |
| docs/web-setup-design.md | Historical RC4/RC5 design; consolidate current setup contract, keep evidence. |
| docs/remote-observability-design.md | Historical RC4 design; preserve rationale, route current work to architecture/access code. |
| docs/v2-design.md | Historical contract; stop calling it the current scope. |
| docs/v1-validation.md | Already historical; keep, read only for evidence. |
| docs/rc6-completion-report.md | Historical validation; keep, no mandatory reading. |
| docs/tasks/01-engines-manager.md | Completed plan; keep as history, no active instructions. |
| docs/tasks/02-ming-3.md | Completed plan; keep as history, preserve hardware limitations. |
| docs/tasks/03-kittentts2.md | Completed plan; keep as history, no active release gate. |
| docs/release-*.md (22 files listed below) | Keep as immutable release history; read only for relevant releases. |

Release-note inventory: release-0.3.0-rc.1.md through release-0.3.0-rc.11.md;
release-2.0.0.md; release-2.1.0.md; release-2.2.0-rc.1.md;
release-2.2.1.md; release-2.2.2.md; release-2.2.3.md;
release-2.3.0-rc.1.md; release-2.3.0-rc.4.md; release-2.3.0-rc.5.md;
release-2.3.0-rc.6.md; release-2.3.0-rc.7.md.

Do not relocate release notes without updating scripts/publish-release.ps1, which
looks up docs/release-<installer_version>.md.

PR #38 already proposes docs/release-procedure.md and AGENTS/updater links:
https://github.com/RicardoMalosso/PacTTSClone/pull/38
Its procedure was inspected at 602d10ea0402b6944b7f14adf12221e82dcf825f.
Keep that document; integrate the smaller reading contract with its AGENTS change
rather than creating a second release policy. It is not counted among main's 50.

## Suggested implementation order

1. B1 queue query and B4 dispatcher fault-injection/recovery.
2. B2 ranking/winner eligibility; agree and implement B3 tournament mode semantics.
3. D1 publication evidence gate and D2 CI dependency cleanup.
4. Compact AGENTS and current docs, preserving release history and PR #38.
5. D3 catalogue pagination, D4 translations and D5 persistence boundaries.

No runtime fixes or documentation deletions are included in this audit. No new
release is necessary to record or clean up these findings.
