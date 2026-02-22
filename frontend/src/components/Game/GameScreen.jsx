import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useGame } from '../../context/GameContext.jsx'
import { useWebSocket } from '../../hooks/useWebSocket.js'
import { useAudioPlayer } from '../../hooks/useAudioPlayer.js'
import VotePanel from '../Voting/VotePanel.jsx'

// ── Constants ──────────────────────────────────────────────────────────────────

const PHASE_LABELS = {
  setup: 'Lobby',
  night: '🌙 Night',
  day_discussion: '☀ Discussion',
  day_vote: '⚖ Vote',
  elimination: '⚰ Verdict',
  game_over: 'Game Over',
}

const PHASE_CLASS = {
  night: 'phase-night',
  day_discussion: 'phase-day',
  day_vote: 'phase-vote',
  elimination: 'phase-elimination',
}

const ROLE_INFO = {
  villager:     { icon: '🧑‍🌾', label: 'Villager',     action: null,        actionLabel: null },
  seer:         { icon: '🔮', label: 'Seer',          action: 'investigate', actionLabel: 'Investigate' },
  healer:       { icon: '💚', label: 'Healer',        action: 'protect',     actionLabel: 'Protect' },
  hunter:       { icon: '🏹', label: 'Hunter',        action: null,        actionLabel: null },
  drunk:        { icon: '🍺', label: 'Seer',          action: 'investigate', actionLabel: 'Investigate' },
  shapeshifter: { icon: '🐺', label: 'Shapeshifter',  action: null,        actionLabel: null },
}

const ROLE_DESC = {
  villager:     'You have no special ability. Trust your instincts and convince the village.',
  seer:         'Each night you may investigate one character to learn if they are the Shapeshifter.',
  healer:       'Each night you may protect one character from elimination.',
  hunter:       'If you are eliminated, you may take one character with you as your dying act.',
  drunk:        'You believe you are the Seer — but fate has twisted your gift.',
  shapeshifter: 'You are the hidden evil. Deceive the village and survive.',
}

const SOURCE_STYLE = {
  narrator:    { color: 'var(--accent)',    fontStyle: 'italic' },
  role_reveal: { color: 'var(--accent)',    fontWeight: 600 },
  seer_result: { color: '#60a5fa' },
  ai_character:{ color: 'var(--text)',      fontWeight: 500 },
  system:      { color: 'var(--text-dim)',  fontStyle: 'italic' },
}

// ── Sub-components ──────────────────────────────────────────────────────────────

function LobbyPanel({ gameId, playerCount, isHost, onStart, startLoading, startError }) {
  const canStart = playerCount >= 2

  return (
    <div className="container" style={{ paddingTop: 32 }}>
      {/* Game code */}
      <div
        className="card"
        style={{ textAlign: 'center', marginBottom: 20, borderColor: 'var(--border-accent)' }}
      >
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
          Game Code
        </div>
        <div
          style={{
            fontFamily: 'var(--font-heading)',
            fontSize: '2rem',
            fontWeight: 700,
            color: 'var(--accent)',
            letterSpacing: '0.2em',
          }}
        >
          {gameId}
        </div>
        <p style={{ fontSize: '0.8125rem', marginTop: 6 }}>
          Share this code with your friends
        </p>
      </div>

      {/* Players joined */}
      <div style={{ marginBottom: 24 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 12,
          }}
        >
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Players Joined
          </span>
          <span
            style={{
              fontFamily: 'var(--font-heading)',
              fontSize: '1rem',
              fontWeight: 700,
              color: playerCount >= 2 ? 'var(--success)' : 'var(--text-muted)',
            }}
          >
            {playerCount}
          </span>
        </div>

        {/* Player dots */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {Array.from({ length: Math.max(playerCount, 2) }).map((_, i) => (
            <div
              key={i}
              style={{
                width: 36,
                height: 36,
                borderRadius: '50%',
                background: i < playerCount ? 'var(--accent-glow)' : 'var(--bg-elevated)',
                border: `1px solid ${i < playerCount ? 'var(--border-accent)' : 'var(--border)'}`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '0.75rem',
                color: i < playerCount ? 'var(--accent)' : 'var(--text-dim)',
              }}
            >
              {i < playerCount ? '●' : '○'}
            </div>
          ))}
        </div>
      </div>

      {/* Start / Wait */}
      {isHost ? (
        <div>
          <button
            className="btn btn-primary btn-lg"
            onClick={onStart}
            disabled={!canStart || startLoading}
          >
            {startLoading ? 'Starting…' : '🔥 Start Game'}
          </button>
          {!canStart && (
            <p style={{ fontSize: '0.8125rem', textAlign: 'center', marginTop: 10 }}>
              Need at least 2 players to start
            </p>
          )}
          {startError && (
            <p style={{ color: 'var(--danger)', fontSize: '0.875rem', marginTop: 8 }}>
              {startError}
            </p>
          )}
        </div>
      ) : (
        <div
          style={{
            textAlign: 'center',
            padding: '20px 0',
            color: 'var(--text-muted)',
          }}
        >
          <div
            className="pulse-glow"
            style={{
              width: 12,
              height: 12,
              borderRadius: '50%',
              background: 'var(--accent)',
              margin: '0 auto 12px',
            }}
          />
          Waiting for the host to start…
        </div>
      )}
    </div>
  )
}


function StoryLogPanel({ logRef, storyLog, myCharacterName }) {
  return (
    <div
      ref={logRef}
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '12px 16px',
        maxWidth: 420,
        width: '100%',
        margin: '0 auto',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        minHeight: 120,
        maxHeight: '45vh',
      }}
    >
      {storyLog.length === 0 && (
        <p style={{ textAlign: 'center', color: 'var(--text-dim)', fontSize: '0.8125rem', paddingTop: 16 }}>
          The night is silent…
        </p>
      )}
      {storyLog.map((msg) => {
        const isMe = msg.speaker === myCharacterName
        const style = SOURCE_STYLE[msg.source] ?? {}
        return (
          <div
            key={msg.id}
            style={{
              background: isMe ? 'var(--bg-elevated)' : 'var(--bg-card)',
              border: `1px solid ${isMe ? 'var(--border-accent)' : 'var(--border)'}`,
              borderRadius: 'var(--radius-md)',
              padding: '10px 12px',
              ...style,
            }}
          >
            <div
              style={{
                fontSize: '0.6875rem',
                color: 'var(--text-muted)',
                marginBottom: 4,
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              {msg.speaker ?? 'Narrator'}
              {isMe && (
                <span style={{ color: 'var(--accent)', marginLeft: 6 }}>You</span>
              )}
            </div>
            <div style={{ fontSize: '0.9rem', lineHeight: 1.5 }}>{msg.text}</div>
          </div>
        )
      })}
    </div>
  )
}


function CharacterGridPanel({ players, aiCharacter, myCharacterName }) {
  const all = [
    ...players.map(p => ({ name: p.characterName, alive: p.alive, isAI: false })),
    ...(aiCharacter ? [{ name: aiCharacter.name, alive: aiCharacter.alive, isAI: true }] : []),
  ].filter(c => c.name)

  if (all.length === 0) return null

  return (
    <div className="container" style={{ marginTop: 12 }}>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(80px, 1fr))',
          gap: 8,
        }}
      >
        {all.map((c) => {
          const isMe = c.name === myCharacterName
          return (
            <div
              key={c.name}
              style={{
                background: 'var(--bg-card)',
                border: `1px solid ${isMe ? 'var(--border-accent)' : c.alive ? 'var(--border)' : 'transparent'}`,
                borderRadius: 'var(--radius-md)',
                padding: '8px 6px',
                textAlign: 'center',
                opacity: c.alive ? 1 : 0.4,
              }}
            >
              <div style={{ fontSize: '1.25rem', marginBottom: 4 }}>
                {c.alive ? (isMe ? '🙂' : c.isAI ? '❓' : '🧑') : '💀'}
              </div>
              <div
                style={{
                  fontSize: '0.6rem',
                  color: isMe ? 'var(--accent)' : 'var(--text-muted)',
                  fontWeight: isMe ? 600 : 400,
                  wordBreak: 'break-word',
                  lineHeight: 1.3,
                }}
              >
                {c.name.split(' ').slice(0, 2).join(' ')}
              </div>
              {c.isAI && c.alive && (
                <div style={{ fontSize: '0.5rem', color: 'var(--text-dim)', marginTop: 2 }}>NPC</div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}


function NightActionPanel({ role, candidates, onAction }) {
  const info = ROLE_INFO[role]
  const label = info?.actionLabel ?? 'Choose'
  const isDrunk = role === 'drunk'

  return (
    <div className="container" style={{ marginTop: 16 }}>
      <div className="card">
        <div style={{ marginBottom: 12 }}>
          <span className="phase-indicator phase-night">🌙 Night Action</span>
          {isDrunk && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 6 }}>
              You wake as the Seer. Choose a character to investigate.
            </div>
          )}
          {!isDrunk && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 6 }}>
              {role === 'seer' && 'Investigate one character — are they the Shapeshifter?'}
              {role === 'healer' && 'Protect one character from elimination tonight.'}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {candidates.map((name) => (
            <button
              key={name}
              className="btn btn-ghost"
              style={{ justifyContent: 'space-between', padding: '12px 16px' }}
              onClick={() => onAction(name)}
            >
              <span>{name}</span>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>{label} →</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}


function HunterRevengePanel({ candidates, onRevenge }) {
  return (
    <div className="container" style={{ marginTop: 16 }}>
      <div className="card" style={{ borderColor: 'var(--danger)' }}>
        <div style={{ marginBottom: 12 }}>
          <span className="phase-indicator phase-elimination">🏹 Final Shot</span>
          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: 8 }}>
            You have been eliminated. Choose one character to take with you.
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {candidates.map((name) => (
            <button
              key={name}
              className="btn btn-danger"
              style={{ padding: '12px 16px' }}
              onClick={() => onRevenge(name)}
            >
              Take {name}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}


// clueSent is driven by context (set on clue_accepted from server) so it:
// - persists across phase transitions within a round
// - resets on PHASE_CHANGE so a new round's day_discussion allows a new clue
function SpectatorCluePanel({ onSubmitClue, clueSent }) {
  const [word, setWord] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    const trimmed = word.trim()
    if (!trimmed) return
    onSubmitClue(trimmed)
    // Do NOT set success here — wait for clue_accepted from server via context
  }

  if (clueSent) {
    return (
      <div className="container" style={{ paddingTop: 12 }}>
        <div
          className="card"
          style={{ textAlign: 'center', borderColor: 'var(--border-accent)', padding: '12px 16px' }}
        >
          <p style={{ fontSize: '0.8125rem', color: 'var(--accent)', margin: 0 }}>
            ✦ Your whisper has been carried on the wind…
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="container" style={{ paddingTop: 12 }}>
      <div className="card" style={{ borderColor: 'var(--border-accent)' }}>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 8 }}>
          🕯 You are a spectator. Leave one word as a clue for the living.
        </div>
        <form onSubmit={handleSubmit} style={{ display: 'flex', gap: 8 }}>
          <input
            className="input"
            placeholder="One word…"
            value={word}
            onChange={e => setWord(e.target.value.replace(/[^a-zA-Z\-']/g, ''))}
            maxLength={30}
            style={{ flex: 1 }}
            autoFocus
          />
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!word.trim()}
            style={{ padding: '12px 16px', flexShrink: 0 }}
          >
            Whisper
          </button>
        </form>
      </div>
    </div>
  )
}


function ChatBar({ chatText, onChange, onSubmit }) {
  return (
    <div
      className="container"
      style={{ marginTop: 12, paddingBottom: 8 }}
    >
      <form onSubmit={onSubmit} style={{ display: 'flex', gap: 8 }}>
        <input
          className="input"
          placeholder="Speak to the village…"
          value={chatText}
          onChange={e => onChange(e.target.value)}
          maxLength={200}
          style={{ flex: 1 }}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={!chatText.trim()}
          style={{ padding: '12px 16px', flexShrink: 0 }}
        >
          →
        </button>
      </form>
    </div>
  )
}


function QuickReactionBar({ aliveCharacters, myCharacterName, onReaction }) {
  const [picker, setPicker] = useState(null) // 'suspect' | 'trust' | null
  const targets = aliveCharacters.filter(c => c !== myCharacterName)

  if (picker) {
    return (
      <div className="container" style={{ paddingTop: 0, paddingBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {picker === 'suspect' ? '🔍 I suspect…' : '🤝 I trust…'}
          </span>
          <button
            className="btn btn-ghost btn-sm"
            style={{ padding: '2px 8px', fontSize: '0.75rem' }}
            onClick={() => setPicker(null)}
          >
            ✕
          </button>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {targets.length === 0
            ? <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>No other players alive.</span>
            : targets.map(name => (
              <button
                key={name}
                className="btn btn-ghost btn-sm"
                style={{ fontSize: '0.75rem', padding: '6px 10px' }}
                onClick={() => { onReaction(picker, name); setPicker(null) }}
              >
                {name.split(' ').slice(0, 2).join(' ')}
              </button>
            ))
          }
        </div>
      </div>
    )
  }

  return (
    <div className="container" style={{ paddingTop: 0, paddingBottom: 8 }}>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <button
          className="btn btn-ghost btn-sm"
          style={{ fontSize: '0.75rem', padding: '6px 10px', opacity: targets.length === 0 ? 0.4 : 1 }}
          onClick={() => targets.length > 0 && setPicker('suspect')}
          disabled={targets.length === 0}
        >
          🔍 Suspect…
        </button>
        <button
          className="btn btn-ghost btn-sm"
          style={{ fontSize: '0.75rem', padding: '6px 10px', opacity: targets.length === 0 ? 0.4 : 1 }}
          onClick={() => targets.length > 0 && setPicker('trust')}
          disabled={targets.length === 0}
        >
          🤝 Trust…
        </button>
        <button
          className="btn btn-ghost btn-sm"
          style={{ fontSize: '0.75rem', padding: '6px 10px' }}
          onClick={() => onReaction('agree', '')}
        >
          👍 Agree
        </button>
        <button
          className="btn btn-ghost btn-sm"
          style={{ fontSize: '0.75rem', padding: '6px 10px' }}
          onClick={() => onReaction('information', '')}
        >
          💡 Info
        </button>
      </div>
    </div>
  )
}


function RoleCard({ roleInfo, characterName, role }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        borderTop: '1px solid var(--border)',
        padding: expanded ? '16px' : '10px 16px',
        transition: 'padding 0.2s ease',
        position: 'sticky',
        bottom: 0,
        zIndex: 5,
      }}
    >
      <div className="container" style={{ padding: 0 }}>
        <button
          onClick={() => setExpanded(e => !e)}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            color: 'var(--text)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: '1.25rem' }}>{roleInfo.icon}</span>
            <div style={{ textAlign: 'left' }}>
              <div
                style={{
                  fontFamily: 'var(--font-heading)',
                  fontSize: '0.8125rem',
                  color: 'var(--accent)',
                  fontWeight: 600,
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}
              >
                {characterName ?? 'Your Role'}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {roleInfo.label}
              </div>
            </div>
          </div>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>
            {expanded ? '▼' : '▲'}
          </span>
        </button>

        {expanded && (
          <div style={{ marginTop: 12 }} className="fade-in">
            <p style={{ fontSize: '0.875rem', marginBottom: 0 }}>
              {ROLE_DESC[role] ?? 'Your secret role in Thornwood.'}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}


function NarratorBar({ isPlaying, volume, setVolume }) {
  return (
    <div
      className="container"
      style={{
        paddingTop: 8,
        paddingBottom: 4,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        minHeight: 36,
      }}
    >
      <span
        style={{
          fontSize: '0.6875rem',
          color: isPlaying ? 'var(--accent)' : 'var(--text-dim)',
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
          minWidth: 60,
        }}
      >
        {isPlaying ? '♪ Narrator' : '· Narrator'}
      </span>
      <input
        type="range"
        min="0"
        max="1"
        step="0.05"
        value={volume}
        onChange={e => setVolume(parseFloat(e.target.value))}
        style={{ flex: 1, accentColor: 'var(--accent)', cursor: 'pointer' }}
        aria-label="Narrator volume"
      />
      <span style={{ fontSize: '0.6875rem', color: 'var(--text-dim)', minWidth: 28, textAlign: 'right' }}>
        {Math.round(volume * 100)}%
      </span>
    </div>
  )
}


// ── Main GameScreen ─────────────────────────────────────────────────────────────

export default function GameScreen() {
  const { gameId } = useParams()
  const navigate = useNavigate()
  const { state, dispatch } = useGame()
  const {
    playerId, playerName, phase, characterName, round, isHost,
    players, aiCharacter, storyLog, role, isEliminated,
    nightActionSubmitted, hunterRevengeNeeded, clueSent,
  } = state

  const { connectionStatus, sendMessage } = useWebSocket(gameId, playerId)
  const { isPlaying, volume, setVolume } = useAudioPlayer()

  const logRef = useRef(null)
  const [chatText, setChatText] = useState('')
  const [startLoading, setStartLoading] = useState(false)
  const [startError, setStartError] = useState(null)
  const [lobbyPlayerCount, setLobbyPlayerCount] = useState(players.length)

  // Auto-scroll story log to bottom on new messages
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [storyLog])

  // Navigate to game over screen when phase reaches game_over
  useEffect(() => {
    if (phase === 'game_over' && gameId) {
      navigate(`/gameover/${gameId}`)
    }
  }, [phase, gameId, navigate])

  // Poll player count from REST API during lobby (WS player_joined only fires post-game-start)
  useEffect(() => {
    if (phase !== 'setup' || !gameId) return
    const poll = async () => {
      try {
        const res = await fetch(`/api/games/${gameId}`)
        if (res.ok) {
          const data = await res.json()
          setLobbyPlayerCount(data.player_count ?? 1)
        }
      } catch { /* ignore */ }
    }
    poll()
    const id = setInterval(poll, 2000)
    return () => clearInterval(id)
  }, [phase, gameId])

  // Redirect if no playerId (navigated directly without joining)
  if (!playerId) {
    return (
      <div className="page" style={{ justifyContent: 'center', alignItems: 'center', padding: 32 }}>
        <div className="container" style={{ textAlign: 'center' }}>
          <p>You need to join or create a game first.</p>
          <button
            className="btn btn-primary"
            style={{ marginTop: 16 }}
            onClick={() => navigate('/')}
          >
            Go Home
          </button>
        </div>
      </div>
    )
  }

  // Night action candidates: all alive characters (including AI)
  const aliveCharacters = [
    ...players.filter(p => p.alive && p.characterName).map(p => p.characterName),
    ...(aiCharacter?.alive ? [aiCharacter.name] : []),
  ]

  const handleChat = (e) => {
    e.preventDefault()
    if (!chatText.trim()) return
    sendMessage('message', { text: chatText.trim() })
    setChatText('')
  }

  const handleQuickReaction = (reaction, target) => {
    sendMessage('quick_reaction', { reaction, target })
  }

  const handleNightAction = (target) => {
    const info = ROLE_INFO[role]
    if (!info?.action) return
    sendMessage('night_action', { action: info.action, target })
    dispatch({ type: 'NIGHT_ACTION_SUBMITTED' })
  }

  const handleHunterRevenge = (target) => {
    sendMessage('hunter_revenge', { target })
    dispatch({ type: 'HUNTER_REVENGE_DONE' })
  }

  const handleSpectatorClue = (word) => {
    sendMessage('spectator_clue', { word })
  }

  const handleStartGame = async () => {
    setStartLoading(true)
    setStartError(null)
    try {
      const res = await fetch(`/api/games/${gameId}/start?host_player_id=${playerId}`, {
        method: 'POST',
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? 'Failed to start game')
      }
    } catch (err) {
      setStartError(err.message)
    } finally {
      setStartLoading(false)
    }
  }

  const roleInfo = ROLE_INFO[role]
  const showStoryLog = phase !== 'setup' && phase !== 'day_vote'
  const showNightPanel =
    phase === 'night' && !isEliminated && !nightActionSubmitted && !!ROLE_INFO[role]?.action
  const showCharacterGrid = phase === 'day_discussion' || phase === 'elimination'
  const showChat = phase === 'day_discussion' && !isEliminated
  const showNarratorBar = phase !== 'setup'

  return (
    <div className="page">

      {/* ── Sticky phase header ── */}
      <div
        style={{
          background: 'var(--bg-card)',
          borderBottom: '1px solid var(--border)',
          padding: '10px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'sticky',
          top: 0,
          zIndex: 10,
        }}
      >
        <div>
          <div
            style={{
              fontFamily: 'var(--font-heading)',
              fontSize: '0.9375rem',
              color: 'var(--accent)',
              fontWeight: 600,
            }}
          >
            {characterName || playerName || '…'}
          </div>
          {round > 0 && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Round {round}
            </div>
          )}
        </div>

        <span className={`phase-indicator ${PHASE_CLASS[phase] ?? 'phase-day'}`}>
          {PHASE_LABELS[phase] ?? phase}
        </span>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {isPlaying && (
            <span
              style={{
                fontSize: '0.625rem',
                color: 'var(--accent)',
                letterSpacing: '0.05em',
                textTransform: 'uppercase',
              }}
            >
              ♪
            </span>
          )}
          <div
            title={connectionStatus}
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: connectionStatus === 'connected' ? 'var(--success)' : 'var(--danger)',
              flexShrink: 0,
            }}
          />
        </div>
      </div>

      {/* ── Narrator audio bar ── */}
      {showNarratorBar && (
        <NarratorBar isPlaying={isPlaying} volume={volume} setVolume={setVolume} />
      )}

      {/* ── Main content ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', paddingBottom: 8 }}>

        {/* Lobby */}
        {phase === 'setup' && (
          <LobbyPanel
            gameId={gameId}
            playerCount={lobbyPlayerCount}
            isHost={isHost}
            onStart={handleStartGame}
            startLoading={startLoading}
            startError={startError}
          />
        )}

        {/* Story log */}
        {showStoryLog && (
          <StoryLogPanel
            logRef={logRef}
            storyLog={storyLog}
            myCharacterName={characterName}
          />
        )}

        {/* Day vote */}
        {phase === 'day_vote' && (
          <VotePanel sendMessage={sendMessage} />
        )}

        {/* Hunter revenge */}
        {hunterRevengeNeeded && role === 'hunter' && (
          <HunterRevengePanel
            candidates={aliveCharacters}
            onRevenge={handleHunterRevenge}
          />
        )}

        {/* Night: action panel */}
        {showNightPanel && (
          <NightActionPanel
            role={role}
            candidates={aliveCharacters}
            onAction={handleNightAction}
          />
        )}

        {/* Night: submitted confirmation */}
        {phase === 'night' && !isEliminated && nightActionSubmitted && ROLE_INFO[role]?.action && (
          <div className="container" style={{ paddingTop: 12 }}>
            <p style={{ textAlign: 'center', color: 'var(--success)', fontSize: '0.875rem' }}>
              ✓ Your action has been submitted. Rest now…
            </p>
          </div>
        )}

        {/* Night: villager / hunter (no action) */}
        {phase === 'night' && !isEliminated && !ROLE_INFO[role]?.action && (
          <div className="container" style={{ paddingTop: 12 }}>
            <p style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              🌙 The village sleeps…
            </p>
          </div>
        )}

        {/* Eliminated spectator — clue panel during discussion, plain notice otherwise */}
        {isEliminated && !hunterRevengeNeeded && phase === 'day_discussion' && (
          <SpectatorCluePanel onSubmitClue={handleSpectatorClue} clueSent={clueSent} />
        )}
        {isEliminated && !hunterRevengeNeeded && phase !== 'setup' && phase !== 'day_vote' && phase !== 'day_discussion' && (
          <div className="container" style={{ paddingTop: 12 }}>
            <p style={{ textAlign: 'center', color: 'var(--text-dim)', fontSize: '0.875rem' }}>
              🕯 You watch from beyond…
            </p>
          </div>
        )}

        {/* Character grid */}
        {showCharacterGrid && (
          <CharacterGridPanel
            players={players}
            aiCharacter={aiCharacter}
            myCharacterName={characterName}
          />
        )}

        {/* Chat bar + quick reactions */}
        {showChat && (
          <>
            <ChatBar
              chatText={chatText}
              onChange={setChatText}
              onSubmit={handleChat}
            />
            <QuickReactionBar
              key={round}
              aliveCharacters={aliveCharacters}
              myCharacterName={characterName}
              onReaction={handleQuickReaction}
            />
          </>
        )}
      </div>

      {/* ── Role card (sticky bottom drawer) ── */}
      {roleInfo && phase !== 'setup' && (
        <RoleCard roleInfo={roleInfo} characterName={characterName} role={role} />
      )}
    </div>
  )
}
