"""Episode building: the generic engine behind workflow episode records.

An episode is a durable Snapper record of one bounded activity — a
workflow execution — whose record is the event sequence at native
resolution (snapper-ai docs/EPISODES.md). This module carries the
workflow-agnostic machinery:

- ``EpisodeDefinition`` — the contract a workflow-specific module
  implements: which bus messages are events, how participants are
  recognized, and the completion pass that joins late records.
- ``EpisodeBuilder`` — the engine an agent drives: it watches bus
  traffic, opens the episode on first sight of an execution, appends
  events as they arrive, and runs the definition's completion pass
  before closing.
- ``MonitorEpisodeIngest`` — the REST client for the swf-monitor
  episode ingest endpoints.

A workflow gains an episode record by implementing one definition and
naming it in the episode builder agent's configuration; nothing here
changes.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EpisodeIngestError(Exception):
    """A rejected or failed episode ingest call."""


class MonitorEpisodeIngest:
    """REST client for the swf-monitor episode ingest endpoints.

    Endpoints (token-authenticated):
      POST {base}/api/snapper/episodes/open/
      POST {base}/api/snapper/episodes/append/
      POST {base}/api/snapper/episodes/close/
    """

    def __init__(self, base_url: str, token: str,
                 builder_identity: str, session=None):
        self.base_url = (base_url or "").rstrip("/")
        self.builder_identity = builder_identity
        self.session = session or requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"Token {token}"})

    def _post(self, path: str, payload: Dict) -> Dict:
        url = f"{self.base_url}/api/snapper/episodes/{path}/"
        payload = dict(payload, builder_identity=self.builder_identity)
        try:
            response = self.session.post(url, json=payload, timeout=30)
        except requests.RequestException as exc:
            raise EpisodeIngestError(f"POST {url} failed: {exc}") from exc
        if response.status_code >= 400:
            raise EpisodeIngestError(
                f"POST {url} returned {response.status_code}: "
                f"{response.text[:500]}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise EpisodeIngestError(
                f"POST {url} returned non-JSON: {response.text[:200]}"
            ) from exc

    def open(self, scope: str, episode_id: str, started_at: str,
             label: str = "", kind: str = "",
             summary: Optional[Dict] = None) -> Dict:
        return self._post("open", {
            "scope": scope, "episode_id": episode_id,
            "started_at": started_at, "label": label, "kind": kind,
            "summary": summary or {},
        })

    def append(self, scope: str, episode_id: str,
               events: Optional[List[Dict]] = None,
               participants: Optional[List[Dict]] = None) -> Dict:
        return self._post("append", {
            "scope": scope, "episode_id": episode_id,
            "events": events or [], "participants": participants or [],
        })

    def close(self, scope: str, episode_id: str, ended_at: str,
              summary: Optional[Dict] = None) -> Dict:
        return self._post("close", {
            "scope": scope, "episode_id": episode_id,
            "ended_at": ended_at, "summary": summary or {},
        })

    def _get(self, path: str) -> Dict:
        url = f"{self.base_url}/api/snapper/{path}"
        try:
            response = self.session.get(url, timeout=30)
        except requests.RequestException as exc:
            raise EpisodeIngestError(f"GET {url} failed: {exc}") from exc
        if response.status_code >= 400:
            raise EpisodeIngestError(
                f"GET {url} returned {response.status_code}: "
                f"{response.text[:500]}")
        try:
            return response.json()
        except ValueError as exc:
            raise EpisodeIngestError(
                f"GET {url} returned non-JSON: {response.text[:200]}"
            ) from exc

    def open_episodes(self, scope: str) -> List[Dict]:
        """The scope's episodes without a recorded end."""
        listing = self._get(f"{scope}/episodes/")
        return [e for e in listing.get("episodes", [])
                if not e.get("ended_at")]

    def episode(self, scope: str, episode_id: str) -> Dict:
        """One episode's full record."""
        return self._get(f"{scope}/episodes/{episode_id}/")


class EpisodeDefinition:
    """The workflow-specific contract. Subclass per workflow.

    The builder consults ``matches`` to route bus messages, converts
    them through ``event_from_message`` / ``participants_from_message``,
    and treats ``is_end`` as the execution's end signal. After the end
    signal the builder calls ``completion_poll`` on every tick until it
    returns True or ``completion_deadline_seconds`` passes, then closes
    the episode.
    """

    #: Snapper scope the episodes belong to (e.g. 'testbed').
    scope = ""
    #: Workflow name this definition covers; used by the default
    #: ``matches`` against the execution id prefix.
    workflow_name = ""
    #: Seconds after the end signal within which completion_poll must
    #: finish; the episode closes regardless when the deadline passes.
    completion_deadline_seconds = 1800

    def matches(self, message: Dict) -> bool:
        execution_id = message.get("execution_id") or ""
        return bool(self.workflow_name) and execution_id.startswith(
            f"{self.workflow_name}-"
        )

    def label(self, message: Dict) -> str:
        run_id = message.get("run_id")
        return f"run {run_id}" if run_id else ""

    def started_at(self, message: Dict) -> str:
        """Timezone-aware ISO start for the episode. The default is the
        arrival time; definitions that trust their messages' stamps
        override this with a normalized message time."""
        return utc_now_iso()

    def ended_at(self, message: Dict) -> str:
        """Timezone-aware ISO end for the episode, from the end-signal
        message. Same default and override contract as started_at —
        essential for backfilled episodes, whose close must carry the
        recorded end rather than the replay time."""
        return utc_now_iso()

    def event_from_message(self, message: Dict) -> Optional[Dict]:
        """Bus message -> event dict ``{time, kind, participant,
        counterpart?, payload?}``, or None to ignore the message."""
        raise NotImplementedError

    def participants_from_message(self, message: Dict) -> List[Dict]:
        """Bus message -> participant upserts ``[{id, label?, kind?,
        born_at?, died_at?, detail?}]``."""
        return []

    def is_end(self, message: Dict) -> bool:
        return message.get("msg_type") == "end_run"

    def completion_poll(self, context: "EpisodeContext",
                        ingest: MonitorEpisodeIngest) -> bool:
        """Join late records (workload states, registries) by appending
        further events and participants; return True when complete.
        Called repeatedly after the end signal until True or deadline."""
        return True

    def summary(self, context: "EpisodeContext") -> Dict:
        """The episode's closing summary document."""
        return {}


class EpisodeContext:
    """Mutable per-execution state the builder shares with a definition."""

    def __init__(self, definition: EpisodeDefinition, episode_id: str):
        self.definition = definition
        self.episode_id = episode_id
        self.opened_at = utc_now_iso()
        self.end_seen_at: Optional[str] = None
        self.ended_at: Optional[str] = None
        self.first_message: Optional[Dict] = None
        self.last_message: Optional[Dict] = None
        #: Scratch space for the definition (run ids, task ids, ...).
        self.notes: Dict = {}
        #: Participant ids already reported, so steady message traffic
        #: does not re-upsert its sender on every message.
        self.seen_participants: set = set()


class EpisodeBuilder:
    """The engine: routes bus messages to armed definitions and drives
    each execution's episode through open, append, completion, close.

    The driving agent calls ``handle_message`` for every bus message it
    receives and ``tick`` periodically (heartbeat cadence is enough);
    ticks run completion polls and close episodes past their deadline.
    Ingest failures are logged and surfaced through the return values;
    the builder never raises out of ``handle_message`` or ``tick`` so a
    broken ingest cannot take the listening agent down with it.
    """

    def __init__(self, definitions: List[EpisodeDefinition],
                 ingest: MonitorEpisodeIngest):
        self.definitions = list(definitions)
        self.ingest = ingest
        self.active: Dict[str, EpisodeContext] = {}

    def adopt_open_episodes(self) -> int:
        """Adopt the builder identity's open episodes, so a restarted
        builder resumes what its predecessor left live: an episode
        whose end signal already passed is driven to completion and
        close by the next ticks; one still mid-flight keeps appending
        as its messages arrive. Returns the number adopted."""
        adopted = 0
        scopes = {d.scope for d in self.definitions if d.scope}
        for scope in scopes:
            try:
                open_records = self.ingest.open_episodes(scope)
            except EpisodeIngestError as exc:
                logger.error("open-episode listing failed for %s: %s",
                             scope, exc)
                continue
            for entry in open_records:
                episode_id = entry.get("episode_id")
                if not episode_id or episode_id in self.active:
                    continue
                definition = next(
                    (d for d in self.definitions
                     if d.scope == scope
                     and d.workflow_name == entry.get("kind")), None)
                if definition is None:
                    continue
                try:
                    record = self.ingest.episode(scope, episode_id)
                except EpisodeIngestError as exc:
                    logger.error("episode fetch failed for %s: %s",
                                 episode_id, exc)
                    continue
                context = EpisodeContext(definition, episode_id)
                for event in record.get("events", []):
                    context.seen_participants.add(event.get("participant"))
                    if definition.is_end({"msg_type": event.get("kind")}):
                        context.end_seen_at = utc_now_iso()
                        context.ended_at = event.get("time")
                self.active[episode_id] = context
                adopted += 1
                logger.info("adopted open episode %s (%s)", episode_id,
                            "end seen" if context.end_seen_at
                            else "still live")
        return adopted

    def handle_message(self, message: Dict) -> bool:
        """Route one bus message; returns True if it joined an episode."""
        execution_id = message.get("execution_id")
        if not execution_id:
            return False
        # Arrival stamp: the fallback event time for messages whose
        # writer stamps no timestamp of its own.
        message.setdefault("_received_at", utc_now_iso())
        try:
            for definition in self.definitions:
                if definition.matches(message):
                    break
            else:
                return False
            context = self.active.get(execution_id)
            if context is None:
                context = EpisodeContext(definition, execution_id)
                context.first_message = message
                self.active[execution_id] = context
                self.ingest.open(
                    scope=definition.scope,
                    episode_id=execution_id,
                    started_at=definition.started_at(message),
                    label=definition.label(message),
                    kind=definition.workflow_name,
                )
            context.last_message = message
            event = definition.event_from_message(message)
            participants = [
                entry for entry in definition.participants_from_message(message)
                if not (entry.get("id") in context.seen_participants
                        and "died_at" not in entry)
            ]
            for entry in participants:
                context.seen_participants.add(entry.get("id"))
            if event or participants:
                self.ingest.append(
                    scope=definition.scope,
                    episode_id=execution_id,
                    events=[event] if event else [],
                    participants=participants,
                )
            if definition.is_end(message):
                context.end_seen_at = utc_now_iso()
                context.ended_at = definition.ended_at(message)
            return True
        except EpisodeIngestError as exc:
            logger.error("episode ingest failed for %s: %s",
                         execution_id, exc)
            return False
        except Exception:
            # A definition hook failing on one malformed message must
            # not take down the listening agent.
            logger.exception("episode handling failed for %s",
                             execution_id)
            return False

    def tick(self) -> None:
        """Drive pending completions; safe to call at any cadence."""
        for execution_id in list(self.active):
            context = self.active[execution_id]
            if context.end_seen_at is None:
                continue
            definition = context.definition
            try:
                done = definition.completion_poll(context, self.ingest)
            except Exception as exc:
                logger.error("completion poll failed for %s: %s",
                             execution_id, exc)
                done = False
            deadline_passed = self._deadline_passed(context)
            if not done and not deadline_passed:
                continue
            if deadline_passed and not done:
                logger.warning(
                    "episode %s closed at completion deadline with the "
                    "completion pass unfinished", execution_id)
            try:
                summary = definition.summary(context)
            except Exception as exc:
                logger.error("episode summary failed for %s: %s",
                             execution_id, exc)
                summary = {}
            try:
                self.ingest.close(
                    scope=definition.scope,
                    episode_id=execution_id,
                    ended_at=context.ended_at or context.end_seen_at,
                    summary=summary,
                )
            except EpisodeIngestError as exc:
                # A failed close keeps the episode active for retry on
                # a later tick; adoption after restart covers the rest.
                logger.error("episode close failed for %s: %s",
                             execution_id, exc)
                continue
            del self.active[execution_id]

    def _deadline_passed(self, context: EpisodeContext) -> bool:
        if context.end_seen_at is None:
            return False
        seen = datetime.fromisoformat(context.end_seen_at)
        elapsed = datetime.now(timezone.utc) - seen
        return elapsed.total_seconds() > (
            context.definition.completion_deadline_seconds
        )
