import { useEffect, useRef, useCallback, useState } from 'react'
import { useGame } from '../context/GameContext.jsx'

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000]

export function useWebSocket(gameId, playerId) {
  const { dispatch } = useGame()
  const wsRef = useRef(null)
  const attemptRef = useRef(0)
  const timerRef = useRef(null)
  const mountedRef = useRef(true)
  const [connectionStatus, setConnectionStatus] = useState('disconnected')

  const handleMessage = useCallback((event) => {
    let msg
    try { msg = JSON.parse(event.data) } catch { return }

    // NOTE: All backend messages use flat top-level fields (no `data` wrapper).
    // The frontend sendMessage wraps outgoing messages in { type, data } but
    // incoming messages from the server are sent as flat objects.
    switch (msg.type) {
      case 'connected':
        // msg: { type, playerId, characterName, gameState: { phase, round, players, aiCharacter } }
        dispatch({ type: 'SET_PLAYER', playerId: msg.playerId, characterName: msg.characterName })
        if (msg.gameState) {
          if (msg.gameState.phase) {
            dispatch({ type: 'PHASE_CHANGE', phase: msg.gameState.phase, round: msg.gameState.round ?? 0 })
          }
          if (msg.gameState.players) {
            dispatch({
              type: 'UPDATE_PLAYERS',
              players: msg.gameState.players.map(p => ({
                id: p.id,
                characterName: p.character_name ?? p.characterName ?? '',
                alive: p.alive ?? true,
                connected: p.connected ?? true,
                ready: p.ready ?? false,
              })),
            })
          }
          if (msg.gameState.aiCharacter) {
            dispatch({ type: 'SET_AI_CHARACTER', aiCharacter: msg.gameState.aiCharacter })
          }
        }
        break

      case 'role':
        // msg: { type, role, characterName, characterIntro, description }
        dispatch({
          type: 'SET_ROLE',
          characterName: msg.characterName,
          role: msg.role,
          abilities: [],  // abilities not sent separately; use description if needed
        })
        // Log the role reveal as a private story message
        if (msg.characterIntro) {
          dispatch({
            type: 'ADD_MESSAGE',
            message: {
              speaker: msg.characterName,
              text: msg.characterIntro,
              source: 'role_reveal',
            },
          })
        }
        break

      case 'audio':
        // msg: { type, data: base64pcm, sampleRate }
        // Relay audio chunks to useAudioPlayer via a DOM event to avoid prop drilling
        window.dispatchEvent(new CustomEvent('narrator-audio', { detail: msg.data }))
        break

      case 'transcript':
        // msg: { type, speaker, text, source, [phase], [round] }
        dispatch({
          type: 'ADD_MESSAGE',
          message: {
            speaker: msg.speaker,
            text: msg.text,
            source: msg.source ?? 'narrator',
            phase: msg.phase,
            round: msg.round,
            timestamp: msg.timestamp,
          },
        })
        break

      case 'phase_change':
        // msg: { type, phase, [round] }
        dispatch({ type: 'PHASE_CHANGE', phase: msg.phase, round: msg.round })
        break

      case 'vote_update':
        // msg: { type, votes: { charName: votedFor|null }, tally: { charName: count } }
        dispatch({ type: 'VOTE_UPDATE', voteMap: msg.votes, tally: msg.tally ?? {} })
        break

      case 'elimination':
        // msg: { type, characterName, wasTraitor, role, triggerHunterRevenge, tally }
        dispatch({ type: 'ELIMINATION', character: msg.characterName, wasTraitor: msg.wasTraitor })
        break

      case 'hunter_revenge':
        // msg: { type, hunterCharacter, targetCharacter, targetWasTraitor }
        dispatch({ type: 'ELIMINATION', character: msg.targetCharacter, wasTraitor: msg.targetWasTraitor })
        break

      case 'game_over':
        // msg: { type, winner, reason, characterReveals: [{ characterName, playerName, role }] }
        dispatch({
          type: 'GAME_OVER',
          winner: msg.winner,
          reveals: msg.characterReveals ?? [],
          strategyLog: [],
        })
        break

      case 'seer_result':
        // msg: { type, character, isShapeshifter, text }
        // Private message to the Seer/Drunk player
        dispatch({
          type: 'ADD_MESSAGE',
          message: {
            speaker: 'Oracle',
            text: msg.text,
            source: 'seer_result',
          },
        })
        break

      case 'player_joined': {
        // msg: { type, characterName, count }
        // Only add if we have a characterName (post-start joiners are already in players list)
        if (msg.characterName) {
          dispatch({
            type: 'ADD_PLAYER',
            player: {
              id: `unknown-${msg.characterName}`,  // id not sent in player_joined
              characterName: msg.characterName,
              alive: true,
              connected: true,
              ready: false,
            },
          })
        }
        break
      }

      case 'error':
        // msg: { type, message, code }
        dispatch({ type: 'SET_ERROR', error: msg.message })
        break

      default:
        break
    }
  }, [dispatch])

  const connect = useCallback(() => {
    if (!gameId || !playerId) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    // Use wss:// on HTTPS (production), ws:// on HTTP (local dev)
    // In dev, Vite proxies /ws → ws://localhost:8000 via vite.config.js
    const wsBase = import.meta.env.VITE_WS_URL
      ?? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
    const wsUrl = `${wsBase}/ws/${gameId}?playerId=${playerId}`
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
      // Guard: don't reconnect if the component has unmounted
      if (!mountedRef.current) return
      const delay = RECONNECT_DELAYS[Math.min(attemptRef.current, RECONNECT_DELAYS.length - 1)]
      attemptRef.current++
      timerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => ws.close()
  }, [gameId, playerId, handleMessage, dispatch])

  // sendMessage wraps outgoing messages as { type, data } per the backend protocol
  const sendMessage = useCallback((type, data = {}) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, data }))
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    if (gameId && playerId) connect()
    return () => {
      mountedRef.current = false
      clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [gameId, playerId, connect])

  return { connectionStatus, sendMessage }
}
