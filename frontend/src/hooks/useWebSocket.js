import { useEffect, useRef, useCallback, useState } from 'react'
import { useGame } from '../context/GameContext.jsx'

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000]

export function useWebSocket(gameId, playerId) {
  const { dispatch } = useGame()
  const wsRef = useRef(null)
  const attemptRef = useRef(0)
  const timerRef = useRef(null)
  const [connectionStatus, setConnectionStatus] = useState('disconnected')

  const handleMessage = useCallback((event) => {
    let msg
    try { msg = JSON.parse(event.data) } catch { return }

    switch (msg.type) {
      case 'connected':
        dispatch({ type: 'SET_PLAYER', playerId: msg.data.playerId, playerName: msg.data.playerName, isHost: msg.data.isHost })
        if (msg.data.players) dispatch({ type: 'UPDATE_PLAYERS', players: msg.data.players })
        break
      case 'role':
        dispatch({ type: 'SET_ROLE', characterName: msg.data.characterName, role: msg.data.role, abilities: msg.data.abilities })
        break
      case 'audio':
        // Relay audio chunks to useAudioPlayer via a DOM event to avoid prop drilling
        window.dispatchEvent(new CustomEvent('narrator-audio', { detail: msg.data.chunk }))
        break
      case 'transcript':
        dispatch({ type: 'ADD_MESSAGE', message: { speaker: msg.data.speaker, text: msg.data.text, source: msg.data.source ?? 'narrator', phase: msg.data.phase, round: msg.data.round, timestamp: msg.data.timestamp } })
        break
      case 'phase_change':
        dispatch({ type: 'PHASE_CHANGE', phase: msg.data.phase, round: msg.data.round })
        break
      case 'vote_update':
        dispatch({ type: 'VOTE_UPDATE', votes: msg.data.votes })
        break
      case 'elimination':
        dispatch({ type: 'ELIMINATION', character: msg.data.character, wasTraitor: msg.data.wasTraitor })
        if (msg.data.narration) {
          dispatch({ type: 'ADD_MESSAGE', message: { speaker: 'Narrator', text: msg.data.narration, source: 'narrator' } })
        }
        break
      case 'hunter_revenge':
        dispatch({ type: 'ELIMINATION', character: msg.data.target })
        break
      case 'game_over':
        dispatch({ type: 'GAME_OVER', winner: msg.data.winner, reveals: msg.data.reveals, strategyLog: msg.data.strategyLog })
        break
      case 'player_joined':
        dispatch({ type: 'ADD_PLAYER', player: msg.data })
        break
      case 'error':
        dispatch({ type: 'SET_ERROR', error: msg.data.message })
        break
      default:
        break
    }
  }, [dispatch])

  const connect = useCallback(() => {
    if (!gameId || !playerId) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const host = window.location.hostname
    const wsUrl = `ws://${host}:8000/ws/${gameId}/${playerId}`
    setConnectionStatus('connecting')

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setConnectionStatus('connected')
      attemptRef.current = 0
      dispatch({ type: 'SET_CONNECTED', connected: true })
    }

    ws.onmessage = handleMessage

    ws.onclose = () => {
      setConnectionStatus('disconnected')
      dispatch({ type: 'SET_CONNECTED', connected: false })
      const delay = RECONNECT_DELAYS[Math.min(attemptRef.current, RECONNECT_DELAYS.length - 1)]
      attemptRef.current++
      timerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => ws.close()
  }, [gameId, playerId, handleMessage, dispatch])

  const sendMessage = useCallback((type, data = {}) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, data }))
    }
  }, [])

  useEffect(() => {
    if (gameId && playerId) connect()
    return () => {
      clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [gameId, playerId, connect])

  return { connectionStatus, sendMessage }
}
