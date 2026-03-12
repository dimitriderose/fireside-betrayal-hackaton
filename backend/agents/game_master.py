"""
Game Master Agent — Pure deterministic Python, no LLM.

Responsibilities:
- Phase transitions (Night → Day Discussion → Day Vote → Elimination → Night)
- Night action resolution (Seer, Healer, Shapeshifter, Drunk)
- Vote tallying and tie-breaking
- Win condition checks
- Hunter revenge trigger

All game rules are implemented here. Nothing is hallucinated.
"""
import asyncio
import random
import logging
import uuid
from typing import Optional, Dict, Any, List, Set

from models.game import Phase, Role, GameStatus, GameEvent, ROLE_DISTRIBUTION
from services.firestore_service import get_firestore_service

logger = logging.getLogger(__name__)


class GameMaster:
    """
    Deterministic game logic engine.
    All methods read/write Firestore via FirestoreService.
    """

    # ── Small-game difficulty adjustment (§12.3.9) ────────────────────────────

    # For 3-4 player games the AI has less room to hide, so Hard and Normal are
    # automatically softened one step. 5+ players: no adjustment.
    SMALL_GAME_DIFFICULTY_ADJUSTMENT: Dict[int, Dict[str, str]] = {
        3: {"easy": "easy", "normal": "easy", "hard": "normal"},
        4: {"easy": "easy", "normal": "easy", "hard": "normal"},
    }

    # ── Minimum satisfying game length ────────────────────────────────────────

    # Minimum rounds before a shapeshifter win can be declared.
    # Prevents 4-player games from ending in round 1 after one elimination.
    # Shapeshifter-eliminated (villager win) always ends the game immediately.
    MINIMUM_ROUNDS: Dict[int, int] = {
        3: 3,   # 15–20 min
        4: 3,   # 15–20 min
        5: 3,   # 20–25 min
        6: 4,   # 25–30 min
        7: 4,   # 25–35 min
        8: 5,   # 30–40 min
    }

    EXPECTED_DURATION_DISPLAY: Dict[int, str] = {
        3: "15–20 minutes",
        4: "15–20 minutes",
        5: "20–25 minutes",
        6: "25–30 minutes",
        7: "25–35 minutes",
        8: "30–40 minutes",
    }

    # ── Phase transitions ──────────────────────────────────────────────────────

    PHASE_CYCLE = [
        Phase.NIGHT,
        Phase.DAY_DISCUSSION,
        Phase.DAY_VOTE,
        Phase.ELIMINATION,
    ]

    async def advance_phase(self, game_id: str) -> Phase:
        """
        Advance the game to the next phase in the cycle.
        Night → Day Discussion → Day Vote → Elimination → Night (loops).
        Increments round counter on each Night phase entry.
        Returns the new phase.
        """
        fs = get_firestore_service()
        game = await fs.get_game(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")

        current = game.phase
        if current == Phase.SETUP:
            next_phase = Phase.NIGHT
            new_round = 1
        elif current == Phase.SEANCE:
            # Séance always returns to DAY_DISCUSSION
            next_phase = Phase.DAY_DISCUSSION
            new_round = game.round
        else:
            try:
                idx = self.PHASE_CYCLE.index(current)
            except ValueError:
                raise ValueError(f"Cannot advance from phase {current}")
            next_idx = (idx + 1) % len(self.PHASE_CYCLE)
            next_phase = self.PHASE_CYCLE[next_idx]
            new_round = game.round + 1 if next_phase == Phase.NIGHT else game.round

        await fs.set_phase(game_id, next_phase, new_round if next_phase == Phase.NIGHT else None)
        display_round = new_round if next_phase == Phase.NIGHT else game.round
        logger.info(f"[{game_id}] Phase: {current} → {next_phase} (round {display_round})")
        return next_phase

    # ── Night action resolution ────────────────────────────────────────────────

    async def resolve_night(self, game_id: str) -> Dict[str, Any]:
        """
        Process all night actions in priority order:
          1. Shapeshifter selects a kill target
          2. Healer protects a target (may cancel the kill)
          3. Seer investigates a target (Drunk gets wrong result)

        Returns a result dict:
        {
            "killed": Optional[str],      # character_name, None if protected
            "protected": Optional[str],   # character_name healer saved
            "seer_result": Optional[dict] # {character: str, is_shapeshifter: bool}
            "hunter_triggered": bool,     # True if killed player is a Hunter
        }
        All hidden events are logged to Firestore with visible_in_game=False.
        """
        fs = get_firestore_service()
        game = await fs.get_game(game_id)
        if not game:
            raise ValueError(f"Game {game_id} not found")
        players = await fs.get_alive_players(game_id)
        night_actions = await fs.get_night_actions(game_id)
        ai_char = await fs.get_ai_character(game_id)
        ai_char_2 = game.ai_character_2  # May be None

        # Build role→player_id lookup for alive players
        role_map: Dict[str, str] = {}  # role_value → player_id
        id_to_player = {p.id: p for p in players}
        char_to_player = {p.character_name: p for p in players}

        for p in players:
            if p.role:
                role_map[p.role.value] = p.id

        result: Dict[str, Any] = {
            "killed": None,
            "protected": None,
            "seer_result": None,
            "hunter_triggered": False,
            "bodyguard_sacrifice": False,  # True when bodyguard absorbed the kill
        }

        # ── Step 1: Shapeshifter kill target ─────────────────────────────────
        # Path A: AI is the traitor → look for AI-authored night_target event
        # Path B: Human shapeshifter (random_alignment) → look for human-authored event
        shapeshifter_target: Optional[str] = None
        events = None  # Lazy-loaded; shared across steps to avoid redundant Firestore reads

        # Build a set of ALL valid alive target names (humans + AIs)
        all_alive_names: Set[str] = set(char_to_player.keys())
        if ai_char and ai_char.alive:
            all_alive_names.add(ai_char.name)
        if ai_char_2 and ai_char_2.alive:
            all_alive_names.add(ai_char_2.name)

        # Determine which AI (if any) is the traitor shapeshifter
        ai_traitor = None
        for ai in [ai_char, ai_char_2]:
            if ai and ai.alive and ai.is_traitor:
                ai_traitor = ai
                break

        if ai_traitor:
            # The shapeshifter AI sets the target via a game event of type "night_target".
            # visible_only=False is explicit: night_target events are hidden (visible_in_game=False).
            events = await fs.get_events(game_id, round=game.round, visible_only=False)
            for ev in events:
                if ev.type == "night_target" and ev.actor == ai_traitor.name:
                    # Validate target is still alive (could be human or ai_char_2)
                    if ev.target in all_alive_names and ev.target != ai_traitor.name:
                        shapeshifter_target = ev.target
                    break
            if not shapeshifter_target:
                if players:
                    # Default: kill a random alive player (fallback)
                    shapeshifter_target = random.choice(players).character_name
                    logger.warning(f"[{game_id}] Shapeshifter had no target set — random: {shapeshifter_target}")
                else:
                    logger.warning(f"[{game_id}] Shapeshifter had no target and no alive players — skipping kill")
        else:
            # Human shapeshifter (AI is loyal) — look for human-authored night_target
            human_shapeshifter = next(
                (p for p in players if p.role == Role.SHAPESHIFTER), None
            )
            if human_shapeshifter:
                events = await fs.get_events(game_id, round=game.round, visible_only=False)
                for ev in events:
                    if ev.type == "night_target" and ev.actor == human_shapeshifter.character_name:
                        if ev.target in all_alive_names:
                            shapeshifter_target = ev.target
                        break
                if shapeshifter_target:
                    logger.info(f"[{game_id}] Human shapeshifter {human_shapeshifter.character_name} targets {shapeshifter_target}")

        # ── Step 1b: Resolve AI night actions from events ──────────────────
        # Loyal AI characters' seer/healer/bodyguard actions are stored as
        # GameEvents (not in the human night_actions dict). Event types use the
        # pattern "{fs_field}_night_{role}" e.g. "ai_character_2_night_heal".
        ai_night_events = {}
        if events is None:
            events = await fs.get_events(game_id, round=game.round, visible_only=False)
        for ai, field in [(ai_char, "ai_character"), (ai_char_2, "ai_character_2")]:
            if ai and ai.alive and not ai.is_traitor:
                for ev in events:
                    if ev.type.startswith(f"{field}_night_"):
                        ai_night_events[ev.type] = ev

        # ── Step 2: Healer protection ─────────────────────────────────────────
        healer_id = role_map.get(Role.HEALER.value)
        protected_target: Optional[str] = None
        ai_healer_name: Optional[str] = None
        if healer_id and healer_id in night_actions:
            protected_target = night_actions[healer_id]
            result["protected"] = protected_target
        else:
            # Check AI healer protection (any AI character)
            for key, ev in ai_night_events.items():
                if key.endswith("_night_heal"):
                    protected_target = ev.target
                    ai_healer_name = ev.actor
                    result["protected"] = protected_target
                    break

        # ── Step 2b: Bodyguard protection ────────────────────────────────────
        # Bodyguard absorbs a shapeshifter kill targeting their protected player;
        # the bodyguard dies in their place. Healer cannot prevent bodyguard sacrifice.
        # Priority: Healer block takes precedence when both protect the same target.
        bodyguard_id = role_map.get(Role.BODYGUARD.value)
        bodyguard_target: Optional[str] = None
        ai_bodyguard_name: Optional[str] = None
        if bodyguard_id and bodyguard_id in night_actions:
            bodyguard_target = night_actions[bodyguard_id]
        else:
            # Check AI bodyguard protection (any AI character)
            for key, ev in ai_night_events.items():
                if key.endswith("_night_protect"):
                    bodyguard_target = ev.target
                    ai_bodyguard_name = ev.actor  # track AI bodyguard for sacrifice
                    break

        # ── Step 3: Apply kill (healer → bodyguard → direct hit) ──────────────
        # Priority: Healer block takes precedence when both Healer and Bodyguard
        # protect the same target (target lives, bodyguard is spared).
        # Bodyguard only sacrifices when Healer is NOT also protecting that target.
        # Actual DB elimination is deferred to the caller via eliminate_character().
        if shapeshifter_target:
            if shapeshifter_target == protected_target:
                # Healer blocks: nobody dies
                logger.info(f"[{game_id}] Kill on {shapeshifter_target} blocked by Healer")
            elif shapeshifter_target == bodyguard_target:
                # Bodyguard absorbs: target lives, bodyguard dies (DB write by caller)
                bodyguard_player = id_to_player.get(bodyguard_id)
                if bodyguard_player:
                    result["killed"] = bodyguard_player.character_name
                    result["bodyguard_sacrifice"] = True
                    logger.info(f"[{game_id}] Bodyguard {bodyguard_player.character_name} died protecting {shapeshifter_target}")
                elif ai_bodyguard_name:
                    # AI bodyguard sacrifices itself
                    result["killed"] = ai_bodyguard_name
                    result["bodyguard_sacrifice"] = True
                    logger.info(f"[{game_id}] AI Bodyguard {ai_bodyguard_name} died protecting {shapeshifter_target}")
                else:
                    logger.warning(f"[{game_id}] Bodyguard player not found — sacrifice skipped")
            else:
                result["killed"] = shapeshifter_target
                victim = char_to_player.get(shapeshifter_target)
                if victim:
                    if victim.role == Role.HUNTER:
                        result["hunter_triggered"] = True
                        logger.info(f"[{game_id}] Hunter {shapeshifter_target} was killed — revenge triggered")

        # ── Step 4: Seer investigation ────────────────────────────────────────
        seer_id = role_map.get(Role.SEER.value)
        drunk_id = role_map.get(Role.DRUNK.value)

        # Determine who is the investigating player
        # (Drunk believes they are the Seer and submits an investigation)
        investigating_id: Optional[str] = None
        investigation_target: Optional[str] = None

        if seer_id and seer_id in night_actions:
            investigating_id = seer_id
            investigation_target = night_actions[seer_id]
        elif drunk_id and drunk_id in night_actions:
            # Drunk submitted an investigation — treat them as the "seer" for this
            investigating_id = drunk_id
            investigation_target = night_actions[drunk_id]

        if investigating_id and investigation_target:
            target_player = char_to_player.get(investigation_target)

            # Determine true alignment of investigation target
            true_result = False
            for ai in [ai_char, ai_char_2]:
                if ai and ai.name == investigation_target:
                    true_result = ai.is_traitor
                    break
            else:
                if target_player:
                    true_result = target_player.role == Role.SHAPESHIFTER

            # Drunk gets the wrong answer
            if investigating_id == drunk_id:
                reported_result = not true_result
                logger.info(f"[{game_id}] Drunk investigated {investigation_target} — given WRONG result")
            else:
                reported_result = true_result

            result["seer_result"] = {
                "character": investigation_target,
                "is_shapeshifter": reported_result,
                "investigating_player_id": investigating_id,
            }

        # ── Step 4b: AI Seer investigation ──────────────────────────────────
        # If an AI character has the Seer role and submitted an investigation,
        # compute the result and store it on the AI character for future dialog/voting.
        for key, ev in ai_night_events.items():
            if key.endswith("_night_investigate") and ev.target:
                ai_investigation_target = ev.target
                ai_true_result = False
                for ai in [ai_char, ai_char_2]:
                    if ai and ai.name == ai_investigation_target:
                        ai_true_result = ai.is_traitor
                        break
                else:
                    tp = char_to_player.get(ai_investigation_target)
                    if tp:
                        ai_true_result = tp.role == Role.SHAPESHIFTER
                # Store result as a hidden event for AI context in future rounds
                # Determine which AI field this event belongs to
                ai_seer_field = key.rsplit("_night_investigate", 1)[0]
                await fs.log_event(game_id, GameEvent(
                    id=str(uuid.uuid4()),
                    type="ai_seer_result",
                    round=game.round,
                    phase=Phase.NIGHT,
                    actor=ev.actor,
                    target=ai_investigation_target,
                    data={"is_shapeshifter": ai_true_result, "ai_character": ai_seer_field},
                    visible_in_game=False,
                ))
                logger.info(f"[{game_id}] AI Seer ({ev.actor}) investigated {ai_investigation_target} — result: {'shapeshifter' if ai_true_result else 'not shapeshifter'}")

        # ── Log all actions as hidden events ──────────────────────────────────

        if shapeshifter_target:
            await fs.log_event(game_id, GameEvent(
                id=str(uuid.uuid4()),
                type="night_kill_attempt",
                round=game.round,
                phase=Phase.NIGHT,
                actor=ai_traitor.name if ai_traitor else (ai_char.name if ai_char else "shapeshifter"),
                target=shapeshifter_target,
                data={
                    "blocked": shapeshifter_target != result.get("killed") and not result.get("bodyguard_sacrifice"),
                    "bodyguard_sacrifice": result.get("bodyguard_sacrifice", False),
                },
                visible_in_game=False,
            ))

        if result.get("bodyguard_sacrifice") and bodyguard_id and bodyguard_id in id_to_player:
            bodyguard_char = id_to_player[bodyguard_id].character_name
            await fs.log_event(game_id, GameEvent(
                id=str(uuid.uuid4()),
                type="bodyguard_sacrifice",
                round=game.round,
                phase=Phase.NIGHT,
                actor=bodyguard_char,
                target=shapeshifter_target,
                visible_in_game=False,
            ))

        if protected_target:
            await fs.log_event(game_id, GameEvent(
                id=str(uuid.uuid4()),
                type="night_heal",
                round=game.round,
                phase=Phase.NIGHT,
                actor=id_to_player[healer_id].character_name if healer_id in id_to_player else (ai_healer_name or "healer"),
                target=protected_target,
                visible_in_game=False,
            ))

        if result.get("seer_result"):
            sr = result["seer_result"]
            await fs.log_event(game_id, GameEvent(
                id=str(uuid.uuid4()),
                type="night_investigation",
                round=game.round,
                phase=Phase.NIGHT,
                actor=id_to_player[sr["investigating_player_id"]].character_name
                      if sr["investigating_player_id"] in id_to_player else "seer",
                target=sr["character"],
                data={
                    "result": sr["is_shapeshifter"],
                    "is_drunk": investigating_id == drunk_id,
                },
                visible_in_game=False,
            ))

        # Clear night actions for next round
        await fs.clear_night_actions(game_id)

        return result

    # ── Vote tallying ──────────────────────────────────────────────────────────

    async def tally_votes(self, game_id: str) -> Dict[str, Any]:
        """
        Count all votes including the AI character's vote.
        Tie-breaking: random selection among tied characters.

        Returns:
        {
            "result": "eliminated" | "tie" | "no_votes",
            "eliminated": Optional[str],  # character_name
            "tally": Dict[str, int],
            "tied": List[str],           # populated on tie
        }
        """
        fs = get_firestore_service()

        tally = await fs.get_vote_tally(game_id)

        # Include all AI characters' votes
        game = await fs.get_game(game_id)
        if game:
            for ai, field in [(game.ai_character, "ai_character"), (game.ai_character_2, "ai_character_2")]:
                if ai and ai.alive and ai.voted_for:
                    tally[ai.voted_for] = tally.get(ai.voted_for, 0) + 1
                    await fs.update_game(game_id, {f"{field}.voted_for": None})

        if not tally:
            return {"result": "no_votes", "eliminated": None, "tally": {}, "tied": []}

        max_votes = max(tally.values())
        leaders = [char for char, count in tally.items() if count == max_votes]

        if len(leaders) == 1:
            eliminated = leaders[0]
            logger.info(f"[{game_id}] Vote result: {eliminated} eliminated with {max_votes} votes")
            return {
                "result": "eliminated",
                "eliminated": eliminated,
                "tally": tally,
                "tied": [],
            }
        else:
            # Tie: random tiebreak (log this so post-game reveal shows it)
            eliminated = random.choice(leaders)
            logger.info(f"[{game_id}] Vote tie between {leaders} — random pick: {eliminated}")
            return {
                "result": "tie",
                "eliminated": eliminated,
                "tally": tally,
                "tied": leaders,
            }

    # ── Elimination ────────────────────────────────────────────────────────────

    async def eliminate_character(
        self, game_id: str, character_name: str, by_vote: bool = True
    ) -> Dict[str, Any]:
        """
        Eliminate the character from the game.

        Args:
            by_vote: True when eliminated by day vote, False for night kills and
                     hunter revenge (recorded in the event log).

        Returns:
        {
            "was_traitor": bool,           # True if eliminated char was the shapeshifter
            "role": str,                   # role name for reveal
            "needs_hunter_revenge": bool,  # True if hunter was eliminated
            "hunter_character": Optional[str],
        }
        """
        fs = get_firestore_service()
        players = await fs.get_all_players(game_id)
        ai_char = await fs.get_ai_character(game_id)

        game = await fs.get_game(game_id)
        ai_char_2 = game.ai_character_2 if game else None

        eliminated_role = None
        needs_hunter_revenge = False
        hunter_character = None
        found = False
        was_traitor = False

        # Check AI characters first
        for ai, field in [(ai_char, "ai_character"), (ai_char_2, "ai_character_2")]:
            if ai and ai.name == character_name:
                found = True
                await fs.update_game(game_id, {f"{field}.alive": False})
                was_traitor = ai.is_traitor
                eliminated_role = "shapeshifter" if was_traitor else (ai.role.value if ai.role else "villager")
                break

        if not found:
            for p in players:
                if p.character_name == character_name:
                    found = True
                    eliminated_role = p.role.value if p.role else "villager"
                    if p.role == Role.HUNTER:
                        needs_hunter_revenge = True
                        hunter_character = character_name
                    break
            if found:
                await fs.eliminate_by_character(game_id, character_name)
            else:
                logger.warning(f"[{game_id}] eliminate_character: '{character_name}' not found — skipping")

        if found:
            await fs.clear_votes(game_id)

            game = await fs.get_game(game_id)
            await fs.log_event(game_id, GameEvent(
                id=str(uuid.uuid4()),
                type="elimination",
                round=game.round if game else 0,
                phase=Phase.ELIMINATION,
                target=character_name,
                data={
                    "was_traitor": was_traitor,
                    "role": eliminated_role,
                    "by_vote": by_vote,
                },
                visible_in_game=True,
            ))

            logger.info(f"[{game_id}] Eliminated {character_name} (role={eliminated_role}, traitor={was_traitor})")

        return {
            "was_traitor": was_traitor,
            "role": eliminated_role,
            "needs_hunter_revenge": needs_hunter_revenge,
            "hunter_character": hunter_character,
        }

    # ── Win condition check ───────────────────────────────────────────────────

    async def check_win_condition(self, game_id: str) -> Optional[Dict[str, Any]]:
        """
        Check if the game is over.

        Villagers win: the shapeshifter is eliminated (always immediate, no round floor).
        Shapeshifter wins: non-shapeshifter alive ≤ 1, AND the game has reached the
          minimum round count for this player size (prevents 1-round finishes).

        Returns None if game continues, or:
        {
            "winner": "villagers" | "shapeshifter",
            "reason": str,
        }
        """
        fs = get_firestore_service()

        # Fetch game state and alive players concurrently for a consistent snapshot.
        game, alive_players = await asyncio.gather(
            fs.get_game(game_id),
            fs.get_alive_players(game_id),
        )
        if not game:
            raise ValueError(f"Game {game_id} not found")

        ai_char = game.ai_character
        ai_char_2 = game.ai_character_2

        # ── Determine who the shapeshifter is and whether they're alive ────
        # The shapeshifter could be: ai_character (is_traitor), ai_character_2
        # (is_traitor), or a human player with role=SHAPESHIFTER.
        shapeshifter_alive = False
        shapeshifter_is_human = False

        for ai in [ai_char, ai_char_2]:
            if ai and ai.alive and ai.is_traitor:
                shapeshifter_alive = True

        # Check human players for shapeshifter role
        human_shapeshifter = next(
            (p for p in alive_players if p.role == Role.SHAPESHIFTER), None
        )
        if human_shapeshifter:
            shapeshifter_alive = True
            shapeshifter_is_human = True

        # ── Villager win: shapeshifter eliminated ──────────────────────────
        if not shapeshifter_alive:
            return {
                "winner": "villagers",
                "reason": "The Shapeshifter has been identified and cast out of Thornwood.",
            }

        # ── Count non-shapeshifter alive characters ────────────────────────
        # Include alive humans (excluding human shapeshifter) and alive AIs
        # (excluding AI shapeshifter).
        non_shapeshifter_alive = 0

        for p in alive_players:
            if p.role != Role.SHAPESHIFTER:
                non_shapeshifter_alive += 1

        for ai in [ai_char, ai_char_2]:
            if ai and ai.alive and not ai.is_traitor:
                non_shapeshifter_alive += 1

        # ── Shapeshifter win: non-shapeshifter alive ≤ 1 ──────────────────
        if non_shapeshifter_alive <= 1:
            if non_shapeshifter_alive == 0:
                # Nobody left to oppose — immediate win
                return {
                    "winner": "shapeshifter",
                    "reason": (
                        "The Shapeshifter has eliminated enough villagers to seize Thornwood. "
                        "The village falls into darkness."
                    ),
                }

            # 1 non-shapeshifter left — check minimum round floor.
            total_players = len(game.character_cast)
            if total_players not in self.MINIMUM_ROUNDS:
                logger.warning(
                    "[%s] check_win_condition: unrecognised player count %d — "
                    "MINIMUM_ROUNDS and ROLE_DISTRIBUTION are out of sync",
                    game_id, total_players,
                )
            min_rounds = self.MINIMUM_ROUNDS.get(total_players, 3)
            current_round = game.round

            if current_round < min_rounds:
                logger.info(
                    "[%s] Shapeshifter win deferred — round %d < minimum %d for %d players",
                    game_id, current_round, min_rounds, total_players,
                )
                return None  # Game continues until minimum rounds reached

            return {
                "winner": "shapeshifter",
                "reason": (
                    "The Shapeshifter has eliminated enough villagers to seize Thornwood. "
                    "The village falls into darkness."
                ),
            }

        return None  # Game continues

    def get_effective_difficulty(self, player_count: int, selected_difficulty: str) -> str:
        """
        Return the difficulty that will actually be used for a game.

        For 3-4 player games the AI has fewer humans to hide behind, so Hard/Normal
        are automatically lowered one step (see SMALL_GAME_DIFFICULTY_ADJUSTMENT).
        For 5+ players the selected difficulty is returned unchanged.

        Args:
            player_count:        Number of *human* players (not counting the AI).
            selected_difficulty: The difficulty value chosen by the host
                                 (e.g. "easy", "normal", "hard").

        Returns:
            The effective difficulty string.
        """
        adjustment_map = self.SMALL_GAME_DIFFICULTY_ADJUSTMENT.get(player_count)
        if adjustment_map is None:
            return selected_difficulty  # 5+ players — no adjustment
        return adjustment_map.get(selected_difficulty, selected_difficulty)

    def get_lobby_summary(self, n: int, selected_difficulty: str = "normal") -> Dict[str, Any]:
        """
        Generate a lobby summary dict shown to the host before game start.

        Args:
            n:                   Total character count including the AI (human players + 1).
            selected_difficulty: The difficulty chosen by the host.

        Returns a dict with:
            "summary"             – Human-readable string with role breakdown + duration.
            "effective_difficulty"– The difficulty that will be applied after any adjustment.
            "difficulty_notice"   – Non-empty warning string when an adjustment is made,
                                    empty string otherwise.
        """
        n_ai = 2 if n <= 3 else 1  # 2 humans → 2 AIs, 3+ humans → 1 AI
        n_human = n - n_ai
        distribution = ROLE_DISTRIBUTION.get(n, [])
        role_counts: Dict[str, int] = {}
        for role in distribution:
            role_counts[role] = role_counts.get(role, 0) + 1

        specials = sum(v for k, v in role_counts.items() if k != Role.VILLAGER.value)
        villagers = role_counts.get(Role.VILLAGER.value, 0)
        duration = self.EXPECTED_DURATION_DISPLAY.get(n, "20–30 minutes")

        ai_label = f"{n_ai} mystery character{'s' if n_ai > 1 else ''} hidden among you"
        summary = (
            f"In this game: {specials} special role{'s' if specials != 1 else ''}, "
            f"{villagers} villager{'s' if villagers != 1 else ''}, "
            f"{ai_label}. "
            f"Expected duration: {duration}"
        )

        effective_difficulty = self.get_effective_difficulty(n_human, selected_difficulty)

        if effective_difficulty != selected_difficulty:
            difficulty_notice = (
                f"With only {n_human} players, "
                f"{selected_difficulty.capitalize()} difficulty is adjusted to "
                f"{effective_difficulty.capitalize()} — the AI has less room to hide."
            )
        else:
            difficulty_notice = ""

        min_player_warning = ""
        if n_human < 4:
            min_player_warning = "Games work best with 4+ players. You can still start with fewer."

        return {
            "summary": summary,
            "effective_difficulty": effective_difficulty,
            "difficulty_notice": difficulty_notice,
            "min_player_warning": min_player_warning,
        }

    # ── Role assignment (delegated to this module as a prep utility) ──────────

    async def prepare_game(
        self, game_id: str, player_ids: List[str], difficulty: str = "normal"
    ) -> Dict[str, Any]:
        """
        Validate player count and confirm role distribution for this game.
        Actual role assignment + character name assignment is done by
        the role-assignment feature (feature/role-assignment).

        Returns the planned role distribution dict.
        Raises ValueError if player count is unsupported.
        """
        n = len(player_ids)
        if n not in ROLE_DISTRIBUTION:
            raise ValueError(
                f"Unsupported player count: {n}. Supported: {sorted(ROLE_DISTRIBUTION.keys())}"
            )

        distribution = ROLE_DISTRIBUTION[n]
        role_counts: Dict[str, int] = {}
        for role in distribution:
            role_counts[role] = role_counts.get(role, 0) + 1

        logger.info(f"[{game_id}] Prepared {n}-player game: {role_counts} (difficulty={difficulty})")
        return {
            "player_count": n,
            "roles": distribution,
            "role_counts": role_counts,
            "difficulty": difficulty,
        }

    # ── Hunter revenge ─────────────────────────────────────────────────────────

    async def execute_hunter_revenge(
        self, game_id: str, hunter_character: str, target_character: str
    ) -> Dict[str, Any]:
        """
        Execute the Hunter's death ability: eliminate their chosen target.
        Called after the Hunter is eliminated (day vote or night kill).
        """
        result = await self.eliminate_character(game_id, target_character, by_vote=False)
        logger.info(
            f"[{game_id}] Hunter {hunter_character} revenge kill: {target_character}"
        )

        fs = get_firestore_service()
        game = await fs.get_game(game_id)
        await fs.log_event(game_id, GameEvent(
            id=str(uuid.uuid4()),
            type="hunter_revenge",
            round=game.round if game else 0,
            phase=game.phase if game else Phase.ELIMINATION,
            actor=hunter_character,
            target=target_character,
            data={"was_traitor": result["was_traitor"]},
            visible_in_game=True,
        ))

        return result


# Module-level singleton
game_master = GameMaster()
