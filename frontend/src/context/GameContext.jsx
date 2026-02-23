import { createContext, useContext, useReducer } from 'react'

const initialState = {
  playerId: null,
  playerName: null,
  gameId: null,
  characterName: null,
  role: null,           // villager | seer | healer | hunter | drunk | shapeshifter
  abilities: [],
  isHost: false,
  phase: 'setup',       // setup | night | day_discussion | day_vote | elimination | game_over
  round: 0,
  difficulty: 'normal',
  players: [],          // [{ id, characterName, alive, connected, ready }]
  aiCharacter: null,    // { name: string, alive: boolean } | null
  votes: {},            // { characterName: count } — vote tally from backend
  voteMap: {},          // { characterName: votedFor | null } — who voted for whom
  myVote: null,         // character name this player voted for (null = not voted yet)
  storyLog: [],         // [{ id, speaker, text, source, phase, round, timestamp }]
  winner: null,         // 'villagers' | 'shapeshifter'
  reveals: [],          // [{ characterName, playerName, role }]
  strategyLog: [],      // [{ round: int, events: [{ type, actor, target, data, visible }] }]
  connected: false,
  isEliminated: false,   // true when the local player's character has been eliminated
  nightActionSubmitted: false, // true after seer/healer submits night action
  hunterRevengeNeeded: false,  // true when eliminated Hunter must pick a revenge target
  clueSent: false,             // true after eliminated player submits spectator clue this round
  inPersonMode: false,         // §12.3.16: camera counts raised hands during vote
  highlightReel: [],           // [{ event_type, description, round, audio_b64 }] §12.3.15
  error: null,
}

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
    case 'SET_ROLE':
      return {
        ...state,
        characterName: action.characterName ?? state.characterName,
        role: action.role ?? state.role,
        abilities: action.abilities ?? [],
      }
    case 'SET_AI_CHARACTER':
      return { ...state, aiCharacter: action.aiCharacter }
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
      const isAIEliminated = state.aiCharacter?.name === action.character
      return {
        ...state,
        players: state.players.map(p =>
          p.characterName === action.character ? { ...p, alive: false } : p
        ),
        isEliminated: state.isEliminated || isLocalPlayerEliminated,
        aiCharacter: isAIEliminated
          ? { ...state.aiCharacter, alive: false }
          : state.aiCharacter,
        hunterRevengeNeeded:
          isLocalPlayerEliminated && (action.triggerHunterRevenge ?? false)
            ? true
            : state.hunterRevengeNeeded,
      }
    }
    case 'HUNTER_REVENGE_DONE':
      return { ...state, hunterRevengeNeeded: false }
    case 'NIGHT_ACTION_SUBMITTED':
      return { ...state, nightActionSubmitted: true }
    case 'CLUE_SENT':
      return { ...state, clueSent: true }
    case 'PHASE_CHANGE':
      return {
        ...state,
        phase: action.phase,
        round: action.round ?? state.round,
        nightActionSubmitted: false,
        hunterRevengeNeeded: false,
        clueSent: false,  // reset each phase so new day_discussion in a new round allows a new clue
        // Reset per-round vote state on every phase transition
        votes: {},
        voteMap: {},
        myVote: null,
      }
    case 'GAME_OVER':
      return {
        ...state,
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
      }
    case 'SET_IN_PERSON_MODE':
      return { ...state, inPersonMode: action.inPersonMode }
    case 'SET_HIGHLIGHT_REEL':
      return { ...state, highlightReel: action.segments ?? [] }
    case 'SET_CONNECTED':
      return { ...state, connected: action.connected }
    case 'SET_ERROR':
      return { ...state, error: action.error }
    case 'RESET':
      return initialState
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
