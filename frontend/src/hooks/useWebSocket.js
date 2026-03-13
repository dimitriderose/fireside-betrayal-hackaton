import { useEffect, useRef, useCallback, useState } from 'react'
import { useGame } from '../context/GameContext.jsx'

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000]

export function useWebSocket(gameId, playerId) {
  const { state, dispatch } = useGame()
  const wsRef = useRef(null)
  const attemptRef = useRef(0)
  const timerRef = useRef(null)
  const syncRef = useRef(null)   // sync heartbeat interval
  const mountedRef = useRef(true)
  const lastSeqRef = useRef(0)   // reliable delivery: track highest received seq
  const phaseRef = useRef(state.phase)  // track current phase for sync comparison
  const charNameRef = useRef(state.characterName)  // for local echo dedup
  const [connectionStatus, setConnectionStatus] = useState('disconnected')

  // Keep refs in sync with state
  phaseRef.current = state.phase
  charNameRef.current = state.characterName

  const handleMessage = useCallback((event) => {
    let msg
    try { msg = JSON.parse(event.data) } catch { return }

    // Track reliable delivery sequence numbers
    if (msg.seq) lastSeqRef.current = Math.max(lastSeqRef.current, msg.seq)

    // NOTE: All backend messages use flat top-level fields (no `data` wrapper).
    // The frontend sendMessage wraps outgoing messages in { type, data } but
    // incoming messages from the server are sent as flat objects.
    switch (msg.type) {
      case 'connected':
        // msg: { type, playerId, characterName, role, alive, gameState: { phase, round, players, aiCharacter } }
        dispatch({ type: 'SET_PLAYER', playerId: msg.playerId, characterName: msg.characterName })
        if (msg.role) {
          dispatch({ type: 'SET_ROLE', characterName: msg.characterName, role: msg.role })
        }
        if (msg.alive === false) {
          // Re-derive isEliminated by dispatching a synthetic elimination for ourselves
          dispatch({ type: 'ELIMINATION', character: msg.characterName })
        }
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
          const aiChars = [msg.gameState.aiCharacter, msg.gameState.aiCharacter2].filter(Boolean)
          if (aiChars.length > 0) {
            dispatch({ type: 'SET_AI_CHARACTERS', aiCharacters: aiChars })
          }
          if (msg.gameState.inPersonMode !== undefined) {
            dispatch({ type: 'SET_IN_PERSON_MODE', inPersonMode: msg.gameState.inPersonMode })
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

      case 'narrator_status':
        // msg: { type, status: "thinking" } — model is alive but processing
        window.dispatchEvent(new CustomEvent('narrator-status', { detail: msg.status }))
        break

      case 'scene_image':
        // msg: { type, data: base64png, sceneKey } — §12.3.14
        window.dispatchEvent(new CustomEvent('narrator-scene', { detail: { data: msg.data, sceneKey: msg.sceneKey } }))
        break

      case 'transcript':
        // msg: { type, speaker, text, source, [phase], [round] }
        // Skip server echo of own chat (already shown via local echo in GameScreen)
        if (msg.source === 'player' && msg.speaker === charNameRef.current) break
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
        // msg: { type, phase, [round], [timer_seconds], [players], [aiCharacter], [aiCharacter2], [seq] }
        dispatch({ type: 'PHASE_CHANGE', phase: msg.phase, round: msg.round, timerSeconds: msg.timer_seconds })
        if (msg.players) {
          dispatch({
            type: 'UPDATE_PLAYERS',
            players: msg.players.map(p => ({
              id: p.id,
              characterName: p.character_name ?? p.characterName ?? '',
              alive: p.alive ?? true,
              connected: p.connected ?? true,
              ready: p.ready ?? false,
            })),
          })
        }
        if (msg.aiCharacter || msg.aiCharacter2) {
          const aiChars = [msg.aiCharacter, msg.aiCharacter2].filter(Boolean)
          if (aiChars.length > 0) {
            dispatch({ type: 'SET_AI_CHARACTERS', aiCharacters: aiChars })
          }
        }
        break

      case 'timer_start':
        // msg: { type, phase, timer_seconds } — update timer for the current phase
        dispatch({ type: 'SET_TIMER', phase: msg.phase, timerSeconds: msg.timer_seconds })
        break

      case 'vote_update':
        // msg: { type, votes: { charName: votedFor|null }, tally: { charName: count } }
        dispatch({ type: 'VOTE_UPDATE', voteMap: msg.votes, tally: msg.tally ?? {} })
        break

      case 'speaker_changed':
        // msg: { type, speaker: characterName|null, playerId: id|null }
        dispatch({ type: 'SET_SPEAKER', speaker: msg.speaker, playerId: msg.playerId })
        break

      case 'elimination':
        // msg: { type, characterName, wasTraitor, role, triggerHunterRevenge, tally }
        dispatch({
          type: 'ELIMINATION',
          character: msg.characterName,
          wasTraitor: msg.wasTraitor,
          triggerHunterRevenge: msg.triggerHunterRevenge ?? false,
        })
        break

      case 'hunter_revenge':
        // msg: { type, hunterCharacter, targetCharacter, targetWasTraitor }
        dispatch({ type: 'ELIMINATION', character: msg.targetCharacter, wasTraitor: msg.targetWasTraitor })
        // Clear hunterRevengeNeeded on all clients — the revenge is resolved
        dispatch({ type: 'HUNTER_REVENGE_DONE' })
        break

      case 'game_over':
        // msg: { type, winner, reason, characterReveals: [...], timeline: [...] }
        dispatch({
          type: 'GAME_OVER',
          winner: msg.winner,
          reveals: msg.characterReveals ?? [],
          strategyLog: msg.timeline ?? [],
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

      case 'clue_accepted':
        // msg: { type, word } — server confirms clue was delivered to narrator
        dispatch({ type: 'CLUE_SENT' })
        break

      case 'haunt_confirmed':
        // msg: { type, target, action } — server confirms ghost accusation was recorded
        dispatch({ type: 'HAUNT_CONFIRMED' })
        break

      case 'ghost_message':
        // msg: { type, speaker, text, timestamp } — Ghost Council message (dead players only)
        // Skip server echo of own ghost message (already shown via local echo in GameScreen)
        if (msg.speaker === charNameRef.current) break
        dispatch({
          type: 'ADD_GHOST_MESSAGE',
          message: {
            speaker: msg.speaker,
            text: msg.text,
            timestamp: msg.timestamp,
          },
        })
        break

      case 'camera_vote_result':
        // msg: { type, characterName, handCount, confidence } — §12.3.16
        // Relay to VotePanel via DOM event to avoid prop drilling
        window.dispatchEvent(new CustomEvent('camera-vote-result', {
          detail: { characterName: msg.characterName, handCount: msg.handCount, confidence: msg.confidence },
        }))
        break

      case 'camera_vote_fallback':
        // msg: { type, characterName, reason } — vision failed, fallback to phone voting
        window.dispatchEvent(new CustomEvent('camera-vote-fallback', {
          detail: { characterName: msg.characterName, reason: msg.reason },
        }))
        break

      case 'highlight_reel':
        // msg: { type, segments: [{ event_type, description, round, audio_b64 }] } §12.3.15
        dispatch({ type: 'SET_HIGHLIGHT_REEL', segments: msg.segments ?? [] })
        break

      case 'sync_ack':
        // msg: { type, phase, round } — server's current phase
        // If our local phase doesn't match, force reconnect to get reliable replay
        if (msg.phase && msg.phase !== phaseRef.current) {
          console.warn(`[sync] phase mismatch: local=${phaseRef.current} server=${msg.phase}, reconnecting`)
          wsRef.current?.close()  // triggers onclose → reconnect → replay
        }
        break

      case 'night_targets':
        // msg: { type, candidates: string[] } — backend-filtered list excluding self
        dispatch({ type: 'SET_NIGHT_TARGETS', candidates: msg.candidates })
        break

      case 'vote_candidates':
        // msg: { type, candidates: string[] } — backend-filtered list excluding self
        dispatch({ type: 'SET_VOTE_CANDIDATES', candidates: msg.candidates })
        break

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
    const wsUrl = `${wsBase}/ws/${gameId}?playerId=${playerId}&lastSeq=${lastSeqRef.current}`
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
      console.log('[ws] sending:', type, data)
      wsRef.current.send(JSON.stringify({ type, data }))
    } else {
      console.warn('[ws] message dropped (not connected):', type, data)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    if (gameId && playerId) connect()
    return () => {
      mountedRef.current = false
      clearTimeout(timerRef.current)
      clearInterval(syncRef.current)
      wsRef.current?.close()
    }
  }, [gameId, playerId, connect])

  // Sync heartbeat: every 2s ask the server "what phase are you on?"
  // If there's a mismatch, force reconnect → reliable delivery replays missed events.
  useEffect(() => {
    if (connectionStatus !== 'connected') {
      clearInterval(syncRef.current)
      return
    }
    syncRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'sync' }))
      }
    }, 2000)
    return () => clearInterval(syncRef.current)
  }, [connectionStatus])

  return { connectionStatus, sendMessage }
}
