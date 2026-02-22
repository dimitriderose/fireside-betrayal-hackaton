import { createContext, useContext, useReducer } from 'react'

const initialState = {
  playerId: null,
  playerName: null,
  gameId: null,
  characterName: null,
  role: null,           // villager | seer | healer | hunter | drunk | shapeshifter
  abilities: [],
  isHost: false,
  phase: 'lobby',       // lobby | night | day_discussion | day_vote | elimination | game_over
  round: 0,
  difficulty: 'normal',
  players: [],          // [{ id, characterName, alive, connected, ready }]
  votes: {},            // { characterName: count }
  storyLog: [],         // [{ id, speaker, text, source, phase, round, timestamp }]
  winner: null,         // 'villagers' | 'shapeshifter'
  reveals: [],          // [{ characterName, playerName, role }]
  strategyLog: [],      // [{ round, reasoning, action }]
  connected: false,
  error: null,
}

function gameReducer(state, action) {
  switch (action.type) {
    case 'SET_PLAYER':
      return {
        ...state,
        playerId: action.playerId,
        playerName: action.playerName,
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
        characterName: action.characterName,
        role: action.role,
        abilities: action.abilities ?? [],
      }
    case 'PHASE_CHANGE':
      return { ...state, phase: action.phase, round: action.round ?? state.round }
    case 'UPDATE_PLAYERS':
      return { ...state, players: action.players }
    case 'ADD_PLAYER': {
      const existing = state.players.filter(p => p.id !== action.player.id)
      return { ...state, players: [...existing, action.player] }
    }
    case 'ADD_MESSAGE':
      return {
        ...state,
        storyLog: [
          ...state.storyLog,
          { ...action.message, id: `${Date.now()}-${Math.random()}` },
        ].slice(-200), // keep last 200 messages
      }
    case 'VOTE_UPDATE':
      return { ...state, votes: action.votes }
    case 'ELIMINATION':
      return {
        ...state,
        players: state.players.map(p =>
          p.characterName === action.character ? { ...p, alive: false } : p
        ),
      }
    case 'GAME_OVER':
      return {
        ...state,
        winner: action.winner,
        reveals: action.reveals ?? [],
        strategyLog: action.strategyLog ?? [],
        phase: 'game_over',
      }
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
