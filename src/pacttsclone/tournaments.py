"""Persist comparison results alongside generation history."""

import hashlib
import random
import time
from collections import Counter
from datetime import date, datetime, timedelta
from datetime import time as clock
from itertools import combinations
from threading import Lock
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel

from .twitch_oauth import FEATURE_SCOPES

Period = Literal["today", "week", "range", "winners", "all", "month", "short"]
REMOVED_TAG = "shit from a butt"
DAYS = {"week": 7, "month": 30}
LOCAL_OWNER = "local-owner"
SCHEMA = """
CREATE TABLE IF NOT EXISTS tournaments (
    id TEXT PRIMARY KEY, period TEXT NOT NULL, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tournament_entries (
    tournament TEXT NOT NULL, clip TEXT NOT NULL, removed INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tournament, clip)
);
CREATE TABLE IF NOT EXISTS tournament_matches (
    id TEXT PRIMARY KEY, tournament TEXT NOT NULL, voter TEXT NOT NULL,
    a TEXT NOT NULL, b TEXT NOT NULL, result TEXT
);
CREATE INDEX IF NOT EXISTS tournament_matches_by_voter
    ON tournament_matches (tournament, voter);
CREATE TABLE IF NOT EXISTS elimination_slots (
    tournament TEXT NOT NULL, slot INTEGER NOT NULL,
    a TEXT, b TEXT, match_id TEXT, winner TEXT, resolved INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tournament, slot)
);
CREATE TABLE IF NOT EXISTS tournament_completions (
    tournament TEXT PRIMARY KEY, champion TEXT
);
CREATE TABLE IF NOT EXISTS tournament_reports (
    tournament TEXT NOT NULL, clip TEXT NOT NULL, voter TEXT NOT NULL,
    PRIMARY KEY (tournament, clip, voter)
);
"""


class CreateTournament(BaseModel):
    mode: Literal["elimination"] = "elimination"
    period: Period
    draft_size: Literal[4, 8, 16, 32, 64] = 16
    start_date: date | None = None
    end_date: date | None = None


class Poll(BaseModel):
    match_id: str
    channel: str


class Compare(BaseModel):
    match_id: str
    result: Literal["a", "b", "skip"]


class TournamentStore:
    def __init__(self, service):
        self.service = service
        self.store = service.store
        self.db = self.store.db
        self.create_lock = Lock()
        with self.store.lock:
            self.db.executescript(SCHEMA)

    def _candidate_clips(self, selection, now):
        period = selection.period
        if period == "winners":
            # Existing installations have match records but no completion records.
            for (tournament,) in self.db.execute(
                "SELECT id FROM tournaments WHERE id NOT IN "
                "(SELECT tournament FROM tournament_completions)"
            ).fetchall():
                if not self._elimination(tournament):
                    self._finish_if_complete(tournament, LOCAL_OWNER, self._active(tournament))
            return [
                clip for (clip,) in self.db.execute(
                    "SELECT DISTINCT champion FROM tournament_completions "
                    "WHERE champion IS NOT NULL ORDER BY champion"
                )
            ]

        cutoff = 0
        end = now
        if period in DAYS:
            cutoff = now - DAYS[period] * 86400
        elif period == "today":
            cutoff = datetime.combine(date.fromtimestamp(now), clock.min).timestamp()
        elif period == "range":
            start_date, end_date = selection.start_date, selection.end_date
            if not start_date or not end_date or start_date > end_date:
                raise HTTPException(422, "Choose a beginning and end date in order.")
            try:
                cutoff = datetime.combine(start_date, clock.min).timestamp()
                end = min(
                    now, datetime.combine(end_date + timedelta(days=1), clock.min).timestamp()
                )
            except (OverflowError, OSError, ValueError) as exc:
                raise HTTPException(422, "Choose dates supported by this computer.") from exc

        return [
            clip
            for (clip,) in self.db.execute(
                """SELECT id FROM records WHERE kind='job'
                AND json_extract(data,'$.status')='succeeded'
                AND COALESCE(json_extract(data,'$.finished_at'),
                             json_extract(data,'$.created_at')) >= ?
                AND COALESCE(json_extract(data,'$.finished_at'),
                             json_extract(data,'$.created_at')) < ?
                ORDER BY id""",
                (cutoff, end),
            )
        ]

    def create(self, selection: CreateTournament):
        with self.create_lock:
            return self._create(selection)

    def _create(self, selection: CreateTournament):
        now = time.time()
        period = selection.period
        with self.store.lock, self.db:
            jobs = self._candidate_clips(selection, now)
            if period == "short":
                appearances = dict(self.db.execute(
                    "SELECT e.clip,COUNT(*) FROM tournament_entries e JOIN tournaments t "
                    "ON t.id=e.tournament WHERE t.period='short' GROUP BY e.clip"
                ))
                random.shuffle(jobs)
                jobs.sort(key=lambda clip: appearances.get(clip, 0))
        entries = {}
        for clip in jobs:
            path = self.service.output_path(clip)
            try:
                if not path.is_file() or not path.stat().st_size:
                    continue
                with path.open("rb") as audio:
                    entries.setdefault(hashlib.file_digest(audio, "sha256").digest(), clip)
            except OSError:
                continue
            if period == "short" and len(entries) == selection.draft_size:
                break
        if len(entries) < 2:
            if period == "short":
                raise HTTPException(422, "Random draft needs at least two distinct generated MP3s.")
            if period == "winners":
                raise HTTPException(422, "At least two distinct previous winners are needed.")
            raise HTTPException(422, "This selection needs at least two distinct generated MP3s.")
        tournament = uuid4().hex
        with self.store.lock, self.db:
            self.db.execute("INSERT INTO tournaments VALUES (?,?,?)", (tournament, period, now))
            self.db.executemany(
                "INSERT INTO tournament_entries (tournament,clip) VALUES (?,?)",
                [(tournament, clip) for clip in entries.values()],
            )
            seeds = list(entries.values())
            random.shuffle(seeds)
            half = 1 << ((len(seeds) - 1).bit_length() - 1)
            seeds.extend([None] * (2 * half - len(seeds)))
            self.db.executemany(
                "INSERT INTO elimination_slots (tournament,slot,a,b) VALUES (?,?,?,?)",
                [(tournament, slot, None, None) for slot in range(1, half)]
                + [(tournament, half + i, seeds[i], seeds[half + i]) for i in range(half)],
            )
            self._advance_elimination(tournament, LOCAL_OWNER, set(entries.values()))
        return {"id": tournament, "period": period, "created_at": now}

    def list(self):
        with self.store.lock:
            return [
                {"id": tournament, "period": period, "created_at": created}
                for tournament, period, created in self.db.execute(
                    "SELECT id,period,created_at FROM tournaments ORDER BY created_at DESC"
                )
            ]

    def _active(self, tournament):
        if not self.db.execute("SELECT 1 FROM tournaments WHERE id=?", (tournament,)).fetchone():
            raise HTTPException(404, "Tournament not found.")
        return {
            clip
            for (clip,) in self.db.execute(
                "SELECT clip FROM tournament_entries WHERE tournament=? AND removed=0",
                (tournament,),
            )
            if self.service.output_path(clip).is_file()
        }

    def _results(self, tournament, active):
        return [
            (a, b, result)
            for a, b, result in self.db.execute(
                "SELECT a,b,result FROM tournament_matches WHERE tournament=? "
                "AND result IN ('a','b')",
                (tournament,),
            )
            if a in active and b in active
        ]

    def _finish_if_complete(self, tournament, voter, active):
        resolved = {
            tuple(sorted((a, b)))
            for a, b in self.db.execute(
                "SELECT a,b FROM tournament_matches WHERE tournament=? AND voter=? "
                "AND result IS NOT NULL",
                (tournament, voter),
            )
            if a in active and b in active
        }
        if len(resolved) != len(active) * (len(active) - 1) // 2:
            return
        results = self._results(tournament, active)
        ranked = rank_clips(active, results)
        champion = None
        if results and len(ranked) >= 2 and ranked[0]["score"] - ranked[1]["score"] > 1e-6:
            champion = ranked[0]["clip"]
        self.db.execute(
            "INSERT OR IGNORE INTO tournament_completions VALUES (?,?)",
            (tournament, champion),
        )

    def _elimination(self, tournament):
        return self.db.execute(
            "SELECT 1 FROM elimination_slots WHERE tournament=? AND slot=1", (tournament,)
        ).fetchone() is not None

    def _advance_elimination(self, tournament, voter, active):
        slots = self.db.execute(
            """SELECT s.slot,s.a,s.b,s.match_id,s.winner,s.resolved,m.result
               FROM elimination_slots s LEFT JOIN tournament_matches m ON m.id=s.match_id
               WHERE s.tournament=? ORDER BY s.slot DESC""",
            (tournament,),
        ).fetchall()
        winners = {}
        pending = None
        for slot, a, b, match_id, winner, resolved, result in slots:
            if resolved:
                winners[slot] = winner
                continue
            if 2 * slot <= len(slots):
                if 2 * slot not in winners or 2 * slot + 1 not in winners:
                    continue
                a, b = winners[2 * slot], winners[2 * slot + 1]
            contenders = [clip for clip in (a, b) if clip in active]
            if result in {"a", "b"}:
                winner = a if result == "a" else b
            elif len(contenders) < 2:
                winner = next(iter(contenders), None)
            else:
                if not match_id:
                    match_id = uuid4().hex
                    self.db.execute(
                        "INSERT INTO tournament_matches VALUES (?,?,?,?,?,NULL)",
                        (match_id, tournament, voter, a, b),
                    )
                    self.db.execute(
                        "UPDATE elimination_slots SET a=?,b=?,match_id=? "
                        "WHERE tournament=? AND slot=?",
                        (a, b, match_id, tournament, slot),
                    )
                if pending is None:
                    pending = {"id": match_id, "a": a, "b": b}
                continue
            winners[slot] = winner
            self.db.execute(
                "UPDATE elimination_slots SET a=?,b=?,winner=?,resolved=1 "
                "WHERE tournament=? AND slot=?",
                (a, b, winner, tournament, slot),
            )
        if 1 in winners:
            champion = winners[1] if winners[1] in active else None
            self.db.execute(
                "INSERT OR REPLACE INTO tournament_completions VALUES (?,?)",
                (tournament, champion),
            )
        return pending

    def pair(self, tournament, voter):
        with self.store.lock, self.db:
            active = self._active(tournament)
            if self._elimination(tournament):
                return self._advance_elimination(tournament, voter, active)
            seen = set()
            for match, a, b, result in self.db.execute(
                "SELECT id,a,b,result FROM tournament_matches WHERE tournament=? AND voter=?",
                (tournament, voter),
            ):
                if result is None and a in active and b in active:
                    return {"id": match, "a": a, "b": b}
                seen.add(tuple(sorted((a, b))))

            results = self._results(tournament, active)
            counts = Counter(clip for a, b, _ in results for clip in (a, b))
            clips = sorted(active)
            random.shuffle(clips)
            if random.random() < 0.85:
                clips.sort(key=lambda clip: counts[clip])
            for a, b in combinations(clips, 2):
                if tuple(sorted((a, b))) not in seen:
                    if random.randrange(2):
                        a, b = b, a
                    match = uuid4().hex
                    self.db.execute(
                        "INSERT INTO tournament_matches VALUES (?,?,?,?,?,NULL)",
                        (match, tournament, voter, a, b),
                    )
                    return {"id": match, "a": a, "b": b}
            self._finish_if_complete(tournament, voter, active)
            return None

    def require_open_match(self, tournament, voter, match_id):
        with self.store.lock:
            active = self._active(tournament)
            row = self.db.execute(
                "SELECT a,b FROM tournament_matches "
                "WHERE id=? AND tournament=? AND voter=? AND result IS NULL "
                "AND NOT EXISTS (SELECT 1 FROM elimination_slots "
                "WHERE match_id=tournament_matches.id AND resolved=1)",
                (match_id, tournament, voter),
            ).fetchone()
            if row is None or any(clip not in active for clip in row):
                raise HTTPException(409, "This matchup is no longer open.")

    def vote(self, tournament, voter, value):
        with self.store.lock, self.db:
            active = self._active(tournament)
            row = self.db.execute(
                "SELECT a,b,result FROM tournament_matches WHERE id=? AND tournament=? AND voter=?",
                (value.match_id, tournament, voter),
            ).fetchone()
            if row is None:
                raise HTTPException(404, "Match not found.")
            a, b, result = row
            if result == value.result:
                return
            elimination = self._elimination(tournament)
            if elimination and value.result == "skip":
                raise HTTPException(422, "Choose a winner to advance the bracket.")
            resolved = elimination and self.db.execute(
                "SELECT resolved FROM elimination_slots WHERE match_id=?", (value.match_id,)
            ).fetchone()[0]
            if resolved or result is not None or a not in active or b not in active:
                raise HTTPException(409, "This matchup is no longer open.")
            self.db.execute(
                "UPDATE tournament_matches SET result=? WHERE id=?", (value.result, value.match_id)
            )
            if elimination:
                self._advance_elimination(tournament, voter, active)
            else:
                self._finish_if_complete(tournament, voter, active)

    def report_local(self, tournament, voter, clip):
        with self.store.lock, self.db:
            updated = self.db.execute(
                "UPDATE tournament_entries SET removed=1 WHERE tournament=? AND clip=?",
                (tournament, clip),
            )
            if not updated.rowcount:
                raise HTTPException(404, "Tournament clip not found.")
            self.db.execute(
                "INSERT OR IGNORE INTO tournament_reports VALUES (?,?,?)",
                (tournament, clip, voter),
            )
            self.db.execute(
                "DELETE FROM tournament_completions WHERE tournament=?", (tournament,)
            )
            active = self._active(tournament)
            if self._elimination(tournament):
                self._advance_elimination(tournament, voter, active)
            else:
                self._finish_if_complete(tournament, voter, active)
        return {"removed": True, "tag": REMOVED_TAG}

    def _clip_records(self, tournament):
        records = {
            clip: {"wins": 0, "losses": 0, "gold": 0, "silver": 0, "bronze": 0}
            for (clip,) in self.db.execute(
                "SELECT clip FROM tournament_entries WHERE tournament=?", (tournament,)
            )
        }
        for a, b, result in self.db.execute(
            """SELECT m.a,m.b,m.result FROM tournament_matches m
               JOIN tournament_entries a ON a.tournament=m.tournament AND a.clip=m.a
               JOIN tournament_entries b ON b.tournament=m.tournament AND b.clip=m.b
               WHERE m.voter=? AND m.result IN ('a','b') AND a.removed=0 AND b.removed=0
               AND EXISTS (SELECT 1 FROM tournament_entries e WHERE e.tournament=?
                           AND e.clip IN (m.a,m.b))""",
            (LOCAL_OWNER, tournament),
        ):
            winner, loser = (a, b) if result == "a" else (b, a)
            if winner in records:
                records[winner]["wins"] += 1
            if loser in records:
                records[loser]["losses"] += 1

        for slot, loser, champion in self.db.execute(
            """SELECT s.slot,e.clip,c.champion FROM elimination_slots s
               JOIN tournament_completions c ON c.tournament=s.tournament
               LEFT JOIN tournament_matches m ON m.id=s.match_id
               LEFT JOIN tournament_entries e ON e.tournament=s.tournament AND e.removed=0
                   AND e.clip=CASE m.result WHEN 'a' THEN m.b WHEN 'b' THEN m.a END
               WHERE s.slot BETWEEN 1 AND 3 AND c.champion IS NOT NULL
               AND EXISTS (SELECT 1 FROM tournament_entries e WHERE e.tournament=?
                           AND e.clip IN (s.a,s.b,c.champion))""",
            (tournament,),
        ):
            if slot == 1 and champion in records:
                records[champion]["gold"] += 1
            if loser in records:
                records[loser]["silver" if slot == 1 else "bronze"] += 1
        return records

    def _thumbnail(self, clip):
        job = self.store.get("job", clip) or {}
        voice_ids = job.get("voice_ids") or [job.get("voice_id")]
        for voice_id in voice_ids:
            if voice_id:
                voice = self.store.get("voice", voice_id) or {}
                if voice.get("thumbnail_url"):
                    return voice["thumbnail_url"]
        return None

    def bracket(self, tournament, voter):
        with self.store.lock:
            active = self._active(tournament)
            records = self._clip_records(tournament)
            clips = [
                {
                    "id": clip,
                    "thumbnail_url": self._thumbnail(clip),
                    "record": records[clip],
                    "tag": REMOVED_TAG if removed else None,
                    "playable": clip in active
                    or bool(removed and self.service.output_path(clip).is_file()),
                }
                for clip, removed in self.db.execute(
                    "SELECT clip,removed FROM tournament_entries WHERE tournament=? ORDER BY clip",
                    (tournament,),
                )
            ]
            matches = [
                {"a": a, "b": b, "result": result, "counts": a in active and b in active}
                for a, b, result in self.db.execute(
                    "SELECT a,b,result FROM tournament_matches WHERE tournament=? AND voter=? "
                    "ORDER BY rowid DESC",
                    (tournament, voter),
                )
            ]
            if self._elimination(tournament):
                slots = [
                    {"round": slot.bit_length(), "a": a, "b": b, "winner": winner,
                     "resolved": bool(resolved), "played": result in {"a", "b"}}
                    for slot, a, b, winner, resolved, result in self.db.execute(
                        """SELECT s.slot,s.a,s.b,s.winner,s.resolved,m.result
                           FROM elimination_slots s
                           LEFT JOIN tournament_matches m ON m.id=s.match_id
                           WHERE s.tournament=? ORDER BY s.slot""", (tournament,),
                    )
                ]
                champion = self.db.execute(
                    "SELECT champion FROM tournament_completions WHERE tournament=?",
                    (tournament,),
                ).fetchone()
                return {"clips": clips, "matches": matches, "slots": slots,
                        "champion": champion[0] if champion else None}
        return {"clips": clips, "matches": matches}

    def leaderboard(self, tournament):
        with self.store.lock:
            active = self._active(tournament)
            results = self._results(tournament, active)
        return rank_clips(active, results)


def rank_clips(clips, results):
    """Bradley–Terry with one prior win and loss against a fixed-strength opponent."""
    opponents = {clip: Counter() for clip in clips}
    wins = Counter()
    for a, b, result in results:
        opponents[a][b] += 1
        opponents[b][a] += 1
        wins[a if result == "a" else b] += 1
    strength = dict.fromkeys(clips, 1.0)
    for _ in range(100):
        updated = {
            clip: (wins[clip] + 1)
            / (
                2 / (strength[clip] + 1)
                + sum(
                    count / (strength[clip] + strength[other])
                    for other, count in opponents[clip].items()
                )
            )
            for clip in clips
        }
        change = max((abs(updated[c] - strength[c]) for c in clips), default=0)
        strength = updated
        if change < 1e-6:
            break
    rows = []
    for clip, opponents_for_clip in opponents.items():
        comparisons = sum(opponents_for_clip.values())
        rows.append(
            {
                "clip": clip,
                "score": strength[clip],
                "comparisons": comparisons,
                "provisional": comparisons < 5,
            }
        )
    return sorted(rows, key=lambda row: (-row["score"], row["clip"]))


def register_tournament_routes(app, service, accounts):
    store = TournamentStore(service)
    poll_lock = Lock()

    def local_owner(request: Request):
        if request.state.remote_access:
            raise HTTPException(403, "Tournament controls require local access.")

    # The local dashboard represents one owner. Public identities will be verified separately.
    owner = LOCAL_OWNER

    @app.get("/api/tournaments")
    def list_tournaments(request: Request):
        local_owner(request)
        return store.list()

    @app.post("/api/tournaments")
    def create_tournament(request: Request, value: CreateTournament):
        local_owner(request)
        return store.create(value)

    @app.post("/api/tournaments/{tournament}/pair")
    def pair(request: Request, tournament: str):
        local_owner(request)
        return store.pair(tournament, owner)

    @app.post("/api/tournaments/{tournament}/vote")
    def vote(request: Request, tournament: str, value: Compare):
        local_owner(request)
        store.vote(tournament, owner, value)
        return {"ok": True}

    @app.post("/api/tournaments/{tournament}/report/{clip}")
    def report(request: Request, tournament: str, clip: str):
        local_owner(request)
        return store.report_local(tournament, owner, clip)

    @app.post("/api/tournaments/{tournament}/poll")
    def poll(request: Request, tournament: str, value: Poll):
        local_owner(request)
        channel = service.store.get("channel", value.channel)
        if not channel or channel.get("kind") == "general":
            raise HTTPException(404, "Save a Twitch channel first.")
        key = f"{value.match_id}:{value.channel}"
        with poll_lock:
            store.require_open_match(tournament, owner, value.match_id)
            previous = service.store.get("tournament_poll", key)
            if previous:
                return previous
            account = accounts.account(value.channel)
            if FEATURE_SCOPES["polls"] not in account["scopes"]:
                raise HTTPException(403, "Reconnect Twitch with Tournament polls selected.")
            broadcaster = {"broadcaster_id": account["user_id"]}
            latest = accounts.api(
                value.channel, "GET", "/polls", query={**broadcaster, "first": 1}
            ).get("data", [])
            if latest and latest[0]["status"] == "ACTIVE":
                raise HTTPException(409, "A Twitch poll is active. Try again when it ends.")
            store.require_open_match(tournament, owner, value.match_id)
            response = accounts.api(
                value.channel,
                "POST",
                "/polls",
                body={
                    **broadcaster,
                    "title": "Which TTS clip was better?",
                    "choices": [{"title": "Clip A"}, {"title": "Clip B"}],
                    "duration": 30,
                    "channel_points_voting_enabled": False,
                },
            )
            return service.store.put("tournament_poll", key, {"id": response["data"][0]["id"]})

    @app.get("/api/tournaments/{tournament}/bracket")
    def bracket(request: Request, tournament: str):
        local_owner(request)
        return store.bracket(tournament, owner)

    @app.get("/api/tournaments/{tournament}/leaderboard")
    def leaderboard(request: Request, tournament: str):
        local_owner(request)
        return store.leaderboard(tournament)
