import { createContext, useContext, useReducer } from 'react'

const SESSION_KEYS = ['playerId', 'playerName', 'gameId', 'isHost']

function safeGet(key) {
  try { return sessionStorage.getItem(key) } catch { return null }
}

function clearSession() {
  try {
    SESSION_KEYS.forEach(k => sessionStorage.removeItem(k))
    sessionStorage.removeItem('roleRevealShown')  // Issue 19
  } catch { /* ignore */ }
}

function createInitialState() {
  return {
    playerId: safeGet('playerId'),
    playerName: safeGet('playerName'),
    gameId: safeGet('gameId'),
    characterName: null,
    role: null,           // villager | seer | healer | hunter | drunk | bodyguard | tanner | shapeshifter
    abilities: [],
    isHost: safeGet('isHost') === 'true',
    phase: 'setup',       // setup | night | day_discussion | day_vote | elimination | seance | game_over
    round: 0,
    difficulty: 'normal',
    players: [],          // [{ id, characterName, alive, connected, ready }]
    aiCharacters: [],     // [{ name: string, alive: boolean }, ...]
    votes: {},            // { characterName: count } — vote tally from backend
    voteMap: {},          // { characterName: votedFor | null } — who voted for whom
    myVote: null,         // character name this player voted for (null = not voted yet)
    storyLog: [],         // [{ id, speaker, text, source, phase, round, timestamp }]
    winner: null,         // 'villagers' | 'shapeshifter' | 'tanner'
    reveals: [],          // [{ characterName, playerName, role }]
    strategyLog: [],      // [{ round: int, events: [{ type, actor, target, data, visible }] }]
    connected: false,
    isEliminated: false,   // true when the local player's character has been eliminated
    nightActionSubmitted: false, // true after seer/healer submits night action
    hunterRevengeNeeded: false,  // true when eliminated Hunter must pick a revenge target
    clueSent: false,             // true after eliminated player submits spectator clue this round
    hauntUsed: false,            // true after eliminated player submits haunt (accuse) this round
    ghostMessages: [],           // [{ speaker, text, timestamp }] — Ghost Council messages (dead players only)
    showRoleReveal: false,       // true when role reveal overlay should be displayed
    inPersonMode: false,         // §12.3.16: camera counts raised hands during vote
    highlightReel: [],           // [{ event_type, description, round, audio_b64 }] §12.3.15
    currentSpeaker: null,        // character name of the player currently speaking (push-to-talk)
    currentSpeakerId: null,      // player ID of the current speaker
    nightTargets: null,          // string[] | null — backend-filtered night action targets (excludes self)
    voteCandidates: null,        // string[] | null — backend-filtered vote candidates (excludes self)
    lastVoteResult: null,        // { tally, individualVotes, eliminated, wasTraitor, role, isTie }
    latestAudioChunk: null,      // Issue 18: latest base64 PCM audio chunk from narrator
    audioChunkCounter: 0,        // monotonic counter so consumers can detect new chunks
    sceneImageCache: {},         // Issue 18: { sceneKey: base64PNG } cache
    currentSceneKey: null,       // Issue 18: active scene key identifier
    cameraVoteResult: null,      // Issue 18: { characterName, handCount, confidence } or { fallback, characterName, reason }
    investigations: [],          // [{ round, target, result, isShapeshifter }] — Seer investigation journal
    voteHistory: [],             // [{ round, tally, individualVotes, eliminated, wasTraitor, role, isTie }]
    activeTab: 'story',          // 'story' | 'journal' | 'records'
    transitionOverlay: null,     // 'dark' | 'dawn' | 'dusk' | null — phase transition fade
    error: null,
  }
}

const initialState = createInitialState()

function gameReducer(state, action) {
  switch (action.type) {
    case 'SET_PLAYER':
      return {
        ...state,
        playerId: action.playerId ?? state.playerId,
        playerName: action.playerName ?? state.playerName,
        characterName: action.characterName ?? state.characterName,
        isHost: action.isHost ?? state.isHost,
      }
    case 'SET_GAME':
      return {
        ...state,
        gameId: action.gameId,
        difficulty: action.difficulty ?? state.difficulty,
      }
    case 'SET_ROLE': {
      // Issue 19: check sessionStorage to make role reveal idempotent across reconnects
      const alreadyRevealed = (() => {
        try { return sessionStorage.getItem('roleRevealShown') === 'true' } catch { return false }
      })()
      return {
        ...state,
        characterName: action.characterName ?? state.characterName,
        role: action.role ?? state.role,
        abilities: action.abilities ?? [],
        showRoleReveal: !state.role && !alreadyRevealed,  // only show on first assignment, not reconnect
      }
    }
    case 'ROLE_REVEAL_DISMISSED':
      // Issue 19: persist dismissal so reconnects don't re-show the overlay
      try { sessionStorage.setItem('roleRevealShown', 'true') } catch { /* ignore */ }
      return { ...state, showRoleReveal: false }
    case 'SET_AI_CHARACTERS':
      return { ...state, aiCharacters: action.aiCharacters }
    case 'SET_MY_VOTE':
      return { ...state, myVote: action.vote }
    case 'UPDATE_PLAYERS':
      return { ...state, players: action.players }
    case 'ADD_PLAYER': {
      // If we already know this character (from UPDATE_PLAYERS), skip — real entry takes precedence
      if (
        action.player.characterName &&
        state.players.some(p => p.characterName === action.player.characterName)
      ) {
        return state
      }
      const existing = state.players.filter(p => p.id !== action.player.id)
      return { ...state, players: [...existing, action.player] }
    }
    case 'ADD_MESSAGE':
      return {
        ...state,
        storyLog: [
          ...state.storyLog,
          { ...action.message, id: action.message.id ?? `${Date.now()}-${Math.random()}` },
        ].slice(-200), // keep last 200 messages
      }
    case 'VOTE_UPDATE': {
      // Ignore stale vote_updates that arrive after the phase has already changed
      if (state.phase !== 'day_vote') return state
      // Restore myVote from voteMap after reconnect (connected message doesn't carry voted_for)
      const restoredVote = action.voteMap?.[state.characterName] ?? state.myVote
      return {
        ...state,
        votes: action.tally ?? state.votes,
        voteMap: action.voteMap ?? state.voteMap,
        myVote: restoredVote,
      }
    }
    case 'ELIMINATION': {
      const isLocalPlayerEliminated = state.characterName === action.character
      return {
        ...state,
        players: state.players.map(p =>
          p.characterName === action.character ? { ...p, alive: false } : p
        ),
        isEliminated: state.isEliminated || isLocalPlayerEliminated,
        aiCharacters: state.aiCharacters.map(ai =>
          ai.name === action.character ? { ...ai, alive: false } : ai
        ),
        hunterRevengeNeeded:
          isLocalPlayerEliminated && (action.triggerHunterRevenge ?? false)
            ? true
            : state.hunterRevengeNeeded,
        lastVoteResult: action.voteResult ?? state.lastVoteResult,
        voteHistory: action.voteResult && !state.voteHistory.some(v => v.round === state.round)
          ? [...state.voteHistory, { round: state.round, ...action.voteResult }]
          : state.voteHistory,
      }
    }
    case 'HUNTER_REVENGE_DONE':
      return { ...state, hunterRevengeNeeded: false }
    case 'NIGHT_ACTION_SUBMITTED':
      return { ...state, nightActionSubmitted: true }
    case 'CLUE_SENT':
      return { ...state, clueSent: true }
    case 'HAUNT_CONFIRMED':
      return { ...state, hauntUsed: true }
    case 'ADD_GHOST_MESSAGE':
      return {
        ...state,
        ghostMessages: [
          ...state.ghostMessages,
          { ...action.message, id: action.message.id ?? `ghost-${Date.now()}-${Math.random()}` },
        ].slice(-100),
      }
    case 'CLEAR_GHOST_MESSAGES':
      return { ...state, ghostMessages: [] }
    case 'SET_NIGHT_TARGETS':
      return { ...state, nightTargets: action.candidates }
    case 'SET_VOTE_CANDIDATES':
      return { ...state, voteCandidates: action.candidates }
    case 'PHASE_CHANGE': {
      const phaseToScene = { night: 'night', day_discussion: 'day_discussion', elimination: 'elimination' }
      const transitionMap = { night: 'dark', seance: 'dark', day_discussion: 'dawn', day_vote: 'judgment', elimination: 'dusk' }
      // Only switch currentSceneKey if the cache already has an image for the new phase key;
      // otherwise keep the previous scene (e.g. "game_started" image from backend).
      const candidateKey = phaseToScene[action.phase]
      const nextSceneKey = (candidateKey && state.sceneImageCache[candidateKey])
        ? candidateKey
        : state.currentSceneKey
      return {
        ...state,
        phase: action.phase,
        round: action.round ?? state.round,
        currentSceneKey: nextSceneKey,
        transitionOverlay: transitionMap[action.phase] ?? null,
        timerSeconds: action.timerSeconds ?? null,  // discussion countdown (null = no timer)
        nightActionSubmitted: false,
        hunterRevengeNeeded: false,
        clueSent: false,  // reset each phase so new day_discussion in a new round allows a new clue
        hauntUsed: false, // reset each phase so new night allows a new haunt
        showRoleReveal: false, // dismiss role reveal on phase transition
        activeTab: 'story', // auto-switch to story on phase change so players don't miss narration
        // Reset per-round vote state on every phase transition
        votes: {},
        voteMap: {},
        myVote: null,
        // Issue 20: clear lastVoteResult on night and day_discussion (start of new round cycle).
        // Keep it during elimination and day_vote phases so tally overlay can show.
        lastVoteResult: (action.phase === 'night' || action.phase === 'day_discussion')
          ? null
          : state.lastVoteResult,
        // Clear push-to-talk speaker on phase transition
        currentSpeaker: null,
        currentSpeakerId: null,
        // Keep candidate lists until backend sends fresh ones via
        // SET_NIGHT_TARGETS / SET_VOTE_CANDIDATES (avoids stale-fallback race)
        nightTargets: state.nightTargets,
        voteCandidates: state.voteCandidates,
      }
    }
    case 'GAME_OVER': {
      // Don't clear session yet — result page needs gameId/playerId for the API call.
      // Session is cleared when the user navigates away from the result page.
      return {
        ...state,
        isHost: false,
        winner: action.winner,
        reveals: action.reveals ?? [],
        strategyLog: action.strategyLog ?? [],
        phase: 'game_over',
        // Reset transient in-round state (PHASE_CHANGE doesn't run for game_over)
        nightActionSubmitted: false,
        hunterRevengeNeeded: false,
        votes: {},
        voteMap: {},
        myVote: null,
        aiCharacters: [],
        ghostMessages: [],
        activeTab: 'story',
        transitionOverlay: null,
      }
    }
    case 'SET_TIMER':
      // Update timerSeconds without resetting other per-phase state
      if (action.phase === state.phase) {
        return { ...state, timerSeconds: action.timerSeconds ?? null }
      }
      return state
    case 'SET_SPEAKER':
      return { ...state, currentSpeaker: action.speaker ?? null, currentSpeakerId: action.playerId ?? null }
    case 'SET_IN_PERSON_MODE':
      return { ...state, inPersonMode: action.inPersonMode }
    case 'SET_HIGHLIGHT_REEL':
      return { ...state, highlightReel: action.segments ?? [] }
    case 'SET_CONNECTED':
      return { ...state, connected: action.connected }
    case 'SET_ERROR':
      return { ...state, error: action.error }
    // Issue 18: new reducer actions for state consolidation
    case 'ADD_AUDIO_CHUNK':
      return {
        ...state,
        latestAudioChunk: action.data,
        audioChunkCounter: state.audioChunkCounter + 1,
      }
    case 'SET_SCENE_IMAGE':
      return {
        ...state,
        sceneImageCache: { ...state.sceneImageCache, [action.sceneKey]: action.data },
        currentSceneKey: action.sceneKey,
      }
    case 'SET_CAMERA_VOTE_RESULT':
      return { ...state, cameraVoteResult: action }
    case 'ADD_INVESTIGATION':
      if (state.investigations.some(i => i.round === action.round && i.target === action.target)) return state
      return {
        ...state,
        investigations: [
          ...state.investigations,
          { round: action.round, target: action.target, result: action.result, isShapeshifter: action.isShapeshifter },
        ],
      }
    case 'SET_ACTIVE_TAB':
      return { ...state, activeTab: action.tab }
    case 'SET_TRANSITION':
      return { ...state, transitionOverlay: action.overlay }
    case 'RESET': {
      clearSession()
      return createInitialState()
    }
    default:
      return state
  }
}

const GameContext = createContext(null)

export function GameProvider({ children }) {
  const [state, dispatch] = useReducer(gameReducer, initialState)
  return (
    <GameContext.Provider value={{ state, dispatch }}>
      {children}
    </GameContext.Provider>
  )
}

export function useGame() {
  const ctx = useContext(GameContext)
  if (!ctx) throw new Error('useGame must be used within <GameProvider>')
  return ctx
}
