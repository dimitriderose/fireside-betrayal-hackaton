import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useGame } from '../../context/GameContext.jsx'
import { useWebSocket } from '../../hooks/useWebSocket.js'
import { useAudioPlayer } from '../../hooks/useAudioPlayer.js'
import { useAudioCapture } from '../../hooks/useAudioCapture.js'
import VotePanel from '../Voting/VotePanel.jsx'
import RoleStrip from './RoleStrip.jsx'

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
  shapeshifter: { icon: '🐺', label: 'Shapeshifter',  action: 'kill',      actionLabel: 'Eliminate' },
  bodyguard:    { icon: '🛡️', label: 'Bodyguard',     action: 'protect',     actionLabel: 'Protect' },
  tanner:       { icon: '🪓', label: 'Tanner',        action: null,        actionLabel: null },
}

const ROLE_DESC = {
  villager:     'You have no special ability. Trust your instincts and convince the village.',
  seer:         'Each night you may investigate one character to learn if they are the Shapeshifter.',
  healer:       'Each night you may protect one character from elimination.',
  hunter:       'If you are eliminated, you may take one character with you as your dying act.',
  drunk:        'You believe you are the Seer — but fate has twisted your gift.',
  shapeshifter: 'You are the hidden evil. Deceive the village and survive.',
  bodyguard:    'Each night protect one character. If the Shapeshifter targets them, you die instead.',
  tanner:       'Your goal is to be voted out by the village. Convince them you are the Shapeshifter.',
}

const SOURCE_STYLE = {
  narrator:    { color: 'var(--accent)',    fontStyle: 'italic' },
  role_reveal: { color: 'var(--accent)',    fontWeight: 600 },
  seer_result: { color: '#60a5fa' },
  ai_character:{ color: 'var(--text)',      fontWeight: 500 },
  system:      { color: 'var(--text-dim)',  fontStyle: 'italic' },
}

// ── Sub-components ──────────────────────────────────────────────────────────────

function LobbyPanel({ gameId, playerCount, lobbySummary, isHost, onStart, startLoading, startError }) {
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

        {/* Player dots — first slot always represents the host */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          {Array.from({ length: Math.max(playerCount, 2) }).map((_, i) => (
            <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3 }}>
              <div
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
                {i === 0 ? '👑' : i < playerCount ? '●' : '○'}
              </div>
              {i === 0 && (
                <span style={{ fontSize: '0.6875rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  host
                </span>
              )}
            </div>
          ))}
        </div>
        {lobbySummary?.summary && (
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 8 }}>
            {lobbySummary.summary}
          </p>
        )}
        {lobbySummary?.difficulty_notice && (
          <p style={{ fontSize: '0.75rem', color: 'var(--warning, #f59e0b)', marginTop: 4 }}>
            {lobbySummary.difficulty_notice}
          </p>
        )}
        {isHost && lobbySummary?.min_player_warning && (
          <p style={{ fontSize: '0.75rem', color: 'var(--warning, #f59e0b)', marginTop: 4 }}>
            {lobbySummary.min_player_warning}
          </p>
        )}
      </div>

      {/* Start / Wait */}
      {isHost ? (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
            <span
              className="badge badge-accent"
              style={{ fontSize: '0.6875rem', padding: '3px 10px' }}
            >
              👑 You are the host
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
              Start when everyone's ready
            </span>
          </div>
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
          <span>Waiting for the </span>
          <span style={{ color: 'var(--accent)' }}>👑 host</span>
          <span> to start…</span>
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


function CharacterGridPanel({ players, myCharacterName, aiCharacter }) {
  const all = players
    .map(p => ({ name: p.characterName, alive: p.alive, isAI: false }))
    .filter(c => c.name)
  if (aiCharacter?.name) {
    all.push({ name: aiCharacter.name, alive: aiCharacter.alive !== false, isAI: true })
  }

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
                {c.alive ? (c.isAI ? '🤖' : isMe ? '🙂' : '🧑') : '💀'}
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
              {role === 'bodyguard' && 'Protect one character. If the Shapeshifter targets them, you die instead.'}
              {role === 'shapeshifter' && 'Choose one character to eliminate tonight.'}
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
  const [fired, setFired] = useState(false)
  const [target, setTarget] = useState(null)

  const handleRevenge = (name) => {
    setFired(true)
    setTarget(name)
    onRevenge(name)
  }

  if (fired) {
    return (
      <div className="container" style={{ marginTop: 16 }}>
        <div className="card fade-in" style={{ borderColor: 'var(--danger)', textAlign: 'center' }}>
          <div style={{ fontSize: '1.5rem', marginBottom: 8 }}>🏹</div>
          <p style={{ color: 'var(--danger)', fontWeight: 600, fontSize: '0.9375rem' }}>
            Your final shot rings out against {target}...
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="container" style={{ marginTop: 16 }}>
      <div className="card" style={{ borderColor: 'var(--danger)' }}>
        <div style={{ marginBottom: 12 }}>
          <span className="phase-indicator phase-elimination">🏹 Final Shot</span>
          <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: 8 }}>
            As the Hunter, you may take one character with you in your final act.
          </div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {candidates.map((name) => (
            <button
              key={name}
              className="btn btn-danger"
              style={{ padding: '12px 16px' }}
              onClick={() => handleRevenge(name)}
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


function ChatBar({ chatText, onChange, onSubmit, isConnected }) {
  return (
    <div
      className="container"
      style={{ marginTop: 12, paddingBottom: 8 }}
    >
      {!isConnected && (
        <div style={{ fontSize: '0.75rem', color: 'var(--danger)', marginBottom: 6, textAlign: 'center' }}>
          Reconnecting to server…
        </div>
      )}
      <form onSubmit={onSubmit} style={{ display: 'flex', gap: 8 }}>
        <input
          className="input"
          placeholder={isConnected ? 'Speak to the village…' : 'Reconnecting…'}
          value={chatText}
          onChange={e => onChange(e.target.value)}
          maxLength={200}
          style={{ flex: 1, opacity: isConnected ? 1 : 0.5 }}
          disabled={!isConnected}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={!chatText.trim() || !isConnected}
          style={{ padding: '12px 16px', flexShrink: 0 }}
        >
          →
        </button>
      </form>
    </div>
  )
}


function QuickReactionBar({ aliveCharacters, myCharacterName, onReaction, onRaiseHand, handRaised }) {
  const [picker, setPicker] = useState(null) // 'suspect' | 'trust' | null
  const [lastReaction, setLastReaction] = useState(null) // brief toast
  const targets = aliveCharacters.filter(c => c !== myCharacterName)

  const handleReaction = (type, name) => {
    onReaction(type, name)
    if (name) setLastReaction(`${type === 'suspect' ? 'Suspected' : 'Trusted'} ${name}`)
    else setLastReaction(type === 'agree' ? 'Agreed' : 'Shared info')
    setPicker(null)
    setTimeout(() => setLastReaction(null), 2000)
  }

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
                onClick={() => handleReaction(picker, name)}
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
          onClick={() => handleReaction('agree', '')}
        >
          👍 Agree
        </button>
        <button
          className="btn btn-ghost btn-sm"
          style={{ fontSize: '0.75rem', padding: '6px 10px' }}
          onClick={() => handleReaction('information', '')}
        >
          💡 Info
        </button>
        <button
          className="btn btn-ghost btn-sm"
          style={{ fontSize: '0.75rem', padding: '6px 10px', opacity: handRaised ? 0.5 : 1 }}
          onClick={onRaiseHand}
          disabled={handRaised}
        >
          {handRaised ? '✋ Hand raised' : '✋ I want to speak'}
        </button>
      </div>
      {lastReaction && (
        <div style={{ fontSize: '0.6875rem', color: 'var(--accent)', marginTop: 4, paddingLeft: 2 }}>
          ✓ {lastReaction}
        </div>
      )}
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


// ── Role Reveal Overlay (shown briefly at game start) ──────────────────────────

function RoleRevealOverlay({ role, characterName, onDismiss }) {
  const info = ROLE_INFO[role] ?? {}
  const desc = ROLE_DESC[role] ?? 'Your secret role in Thornwood.'

  useEffect(() => {
    // Auto-dismiss after 10s, or when first narrator audio arrives
    const timer = setTimeout(onDismiss, 10000)
    const onAudio = () => onDismiss()
    window.addEventListener('narrator-audio', onAudio, { once: true })
    return () => { clearTimeout(timer); window.removeEventListener('narrator-audio', onAudio) }
  }, [onDismiss])

  return (
    <div
      onClick={onDismiss}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        background: 'radial-gradient(ellipse at center, rgba(30,20,10,0.97) 0%, rgba(10,8,6,0.99) 100%)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        cursor: 'pointer',
        animation: 'roleRevealFadeIn 0.6s ease-out',
        padding: 24,
      }}
    >
      <div style={{ fontSize: '4rem', marginBottom: 16, filter: 'drop-shadow(0 0 24px rgba(255,180,60,0.4))' }}>
        {info.icon ?? '❓'}
      </div>
      <div style={{
        fontFamily: 'var(--font-heading)',
        fontSize: '1.75rem',
        fontWeight: 700,
        color: 'var(--accent)',
        textTransform: 'uppercase',
        letterSpacing: '0.15em',
        marginBottom: 8,
        textShadow: '0 0 20px rgba(255,180,60,0.3)',
      }}>
        {info.label ?? role}
      </div>
      {characterName && (
        <div style={{
          fontSize: '1.125rem',
          color: 'var(--text)',
          marginBottom: 16,
          fontWeight: 500,
        }}>
          {characterName}
        </div>
      )}
      <div style={{
        fontSize: '1rem',
        color: 'var(--text-muted)',
        textAlign: 'center',
        maxWidth: 340,
        lineHeight: 1.6,
        marginBottom: 32,
      }}>
        {desc}
      </div>
      <div style={{
        fontSize: '0.75rem',
        color: 'var(--text-dim)',
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        animation: 'roleRevealPulse 2s ease-in-out infinite',
      }}>
        Tap anywhere to continue
      </div>
      <style>{`
        @keyframes roleRevealFadeIn {
          from { opacity: 0; transform: scale(0.95); }
          to   { opacity: 1; transform: scale(1); }
        }
        @keyframes roleRevealPulse {
          0%, 100% { opacity: 0.5; }
          50%      { opacity: 1; }
        }
      `}</style>
    </div>
  )
}


const NARRATOR_SILENCE_MS = 15_000
const NARRATOR_LONG_SILENCE_MS = 30_000

function NarratorBar({ isPlaying, volume, setVolume, storyLog, connectionStatus }) {
  // 0 = normal, 1 = thinking (15s), 2 = long silence (30s)
  const [silenceTier, setSilenceTier] = useState(0)
  const lastLogLen = useRef(storyLog?.length ?? 0)
  const logLen = storyLog?.length ?? 0

  useEffect(() => {
    if (isPlaying || logLen > lastLogLen.current) {
      lastLogLen.current = logLen
      setSilenceTier(0)
    }
    if (isPlaying) return
    if (logLen === 0) return
    const t1 = setTimeout(() => setSilenceTier(1), NARRATOR_SILENCE_MS)
    const t2 = setTimeout(() => setSilenceTier(2), NARRATOR_LONG_SILENCE_MS)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [isPlaying, logLen])

  const disconnected = connectionStatus && connectionStatus !== 'connected'
  const label = disconnected
    ? '⚠ Disconnected'
    : isPlaying
      ? '♪ Narrator'
      : silenceTier >= 2
        ? '… Narrator may be reconnecting'
        : silenceTier >= 1
          ? '… Narrator thinking'
          : '· Narrator'

  const color = disconnected
    ? 'var(--danger)'
    : isPlaying
      ? 'var(--accent)'
      : silenceTier >= 2
        ? 'var(--danger)'
        : silenceTier >= 1
          ? 'var(--warning, #f59e0b)'
          : 'var(--text-dim)'

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
          color,
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
          minWidth: 130,
        }}
      >
        {label}
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
    showRoleReveal, nightTargets, voteCandidates, timerSeconds,
  } = state

  const { connectionStatus, sendMessage } = useWebSocket(gameId, playerId)
  const { isPlaying, volume, setVolume } = useAudioPlayer()
  const { micActive, muted, micError, startCapture, stopCapture, toggleMute } = useAudioCapture(sendMessage)

  const logRef = useRef(null)
  const [chatText, setChatText] = useState('')
  const [startLoading, setStartLoading] = useState(false)
  const [startError, setStartError] = useState(null)
  const [lobbyPlayerCount, setLobbyPlayerCount] = useState(players.length)
  const [lobbySummary, setLobbySummary] = useState(null)
  const [sceneImage, setSceneImage] = useState(null)
  const [nightPanelReady, setNightPanelReady] = useState(false)
  const [dayHintDismissed, setDayHintDismissed] = useState(
    () => localStorage.getItem('dayHintSeen') === '1'
  )

  // ── Discussion countdown timer ──
  const [discussionTimeLeft, setDiscussionTimeLeft] = useState(null)

  useEffect(() => {
    if (phase !== 'day_discussion' || !timerSeconds) {
      setDiscussionTimeLeft(null)
      return
    }
    setDiscussionTimeLeft(timerSeconds)
    const interval = setInterval(() => {
      setDiscussionTimeLeft(prev => (prev > 0 ? prev - 1 : 0))
    }, 1000)
    return () => clearInterval(interval)
  }, [phase, round, timerSeconds])

  // Auto-scroll story log to bottom on new messages
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [storyLog])

  // Navigate to game over screen immediately
  useEffect(() => {
    if (phase === 'game_over' && gameId) {
      navigate(`/gameover/${gameId}`)
    }
  }, [phase, gameId, navigate])

  // Auto-start mic during day_discussion, stop on other phases
  useEffect(() => {
    if (phase === 'day_discussion' && !isEliminated && connectionStatus === 'connected') {
      startCapture()
    } else {
      stopCapture()
    }
  }, [phase, isEliminated, connectionStatus, startCapture, stopCapture])

  // Poll player count from REST API during lobby (WS player_joined only fires post-game-start)
  useEffect(() => {
    if (phase !== 'setup' || !gameId) return
    const poll = async () => {
      try {
        const res = await fetch(`/api/games/${gameId}`)
        if (res.ok) {
          const data = await res.json()
          setLobbyPlayerCount(data.player_count ?? 1)
          setLobbySummary(data.lobby_summary ?? null)
        }
      } catch { /* ignore */ }
    }
    poll()
    const id = setInterval(poll, 2000)
    return () => clearInterval(id)
  }, [phase, gameId])

  // Scene image: listen for narrator-scene custom events (§12.3.14)
  useEffect(() => {
    const handler = (e) => setSceneImage(e.detail.data)
    window.addEventListener('narrator-scene', handler)
    return () => window.removeEventListener('narrator-scene', handler)
  }, [])

  // Fade out scene image on phase transition (new image replaces it when it arrives)
  // Removed instant clear — scene image now persists until replaced by a new one

  // Delay showing the night action panel so the narrator can speak first
  useEffect(() => {
    if (phase === 'night') {
      setNightPanelReady(false)
      const timer = setTimeout(() => setNightPanelReady(true), 8000)
      return () => clearTimeout(timer)
    }
    setNightPanelReady(false)
  }, [phase])

  // Auto-dismiss day hint on phase transition away from day_discussion (state only, not localStorage).
  // Explicit ✕ click writes localStorage for permanent across-game dismissal.
  const prevPhaseRef = useRef(null)
  useEffect(() => {
    if (prevPhaseRef.current === 'day_discussion' && phase !== 'day_discussion' && !dayHintDismissed) {
      setDayHintDismissed(true)
    }
    prevPhaseRef.current = phase
  }, [phase, dayHintDismissed])

  // Redirect if no playerId (navigated directly without joining)
  // Skip this guard during game_over — the useEffect above will navigate to /gameover
  if (!playerId && phase !== 'game_over') {
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

  const [nightActionTarget, setNightActionTarget] = useState(null)
  const handleNightAction = (target) => {
    const info = ROLE_INFO[role]
    if (!info?.action) return
    sendMessage('night_action', { action: info.action, target })
    setNightActionTarget(target)
    dispatch({ type: 'NIGHT_ACTION_SUBMITTED' })
  }

  const handleHunterRevenge = (target) => {
    sendMessage('hunter_revenge', { target })
    dispatch({ type: 'HUNTER_REVENGE_DONE' })
  }

  const handleSpectatorClue = (word) => {
    sendMessage('spectator_clue', { word })
  }

  const [handRaised, setHandRaised] = useState(false)
  const handleRaiseHand = () => {
    sendMessage('raise_hand', { characterName: characterName })
    setHandRaised(true)
    setTimeout(() => setHandRaised(false), 3000)
  }

  const handleStartGame = async () => {
    if (startLoading) return  // guard against double-click
    setStartLoading(true)
    setStartError(null)
    try {
      const res = await fetch(`/api/games/${gameId}/start?host_player_id=${playerId}`, {
        method: 'POST',
      })
      if (res.status === 409) {
        // 409 = "Game is not in lobby state" → already starting, not an error
        return
      }
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
  const showStoryLog = phase !== 'setup'
  const showNightPanel =
    phase === 'night' && !isEliminated && !nightActionSubmitted && !!ROLE_INFO[role]?.action && nightPanelReady
  const showCharacterGrid = phase === 'day_discussion' || phase === 'elimination'
  const showChat = phase === 'day_discussion' && !isEliminated
  const showNarratorBar = phase !== 'setup'

  return (
    <div className="page">

      {/* ── Role reveal overlay (shown briefly at game start) ── */}
      {showRoleReveal && role && (
        <RoleRevealOverlay
          role={role}
          characterName={characterName}
          onDismiss={() => dispatch({ type: 'ROLE_REVEAL_DISMISSED' })}
        />
      )}


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

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={`phase-indicator ${PHASE_CLASS[phase] ?? 'phase-day'}`}>
            {PHASE_LABELS[phase] ?? phase}
          </span>
          {discussionTimeLeft != null && phase === 'day_discussion' && (() => {
            const mins = Math.floor(discussionTimeLeft / 60)
            const secs = discussionTimeLeft % 60
            const timerColor = discussionTimeLeft <= 15
              ? 'var(--danger)'
              : discussionTimeLeft <= 30
                ? '#fbbf24'
                : 'var(--text-muted)'
            return (
              <span
                className={discussionTimeLeft <= 15 ? 'pulse-glow' : ''}
                style={{
                  fontFamily: 'var(--font-heading)',
                  fontSize: '0.875rem',
                  fontWeight: 700,
                  color: timerColor,
                  transition: 'color 0.5s ease',
                  minWidth: 36,
                  textAlign: 'center',
                }}
              >
                {mins}:{secs.toString().padStart(2, '0')}
              </span>
            )
          })()}
        </div>

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
          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <div
              title={connectionStatus}
              className={connectionStatus !== 'connected' ? 'pulse-glow' : ''}
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: connectionStatus === 'connected'
                  ? 'var(--success)'
                  : connectionStatus === 'connecting'
                    ? 'var(--warning, #f59e0b)'
                    : 'var(--danger)',
                flexShrink: 0,
              }}
            />
            {connectionStatus !== 'connected' && (
              <span style={{ fontSize: '0.625rem', color: 'var(--danger)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {connectionStatus === 'connecting' ? 'Connecting' : 'Disconnected'}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* ── Narrator audio bar ── */}
      {showNarratorBar && (
        <NarratorBar isPlaying={isPlaying} volume={volume} setVolume={setVolume} storyLog={storyLog} connectionStatus={connectionStatus} />
      )}

      {/* ── Main content ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', paddingBottom: 8 }}>

        {/* Lobby */}
        {phase === 'setup' && (
          <LobbyPanel
            gameId={gameId}
            playerCount={lobbyPlayerCount}
            lobbySummary={lobbySummary}
            isHost={isHost}
            onStart={handleStartGame}
            startLoading={startLoading}
            startError={startError}
          />
        )}

        {/* Scene image (§12.3.14) — atmospheric illustration sent on phase transitions */}
        {sceneImage && phase !== 'setup' && (
          <div
            className="fade-in"
            style={{ margin: '0 16px 8px', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}
          >
            <img
              src={`data:image/png;base64,${sceneImage}`}
              alt=""
              style={{ width: '100%', display: 'block', opacity: 0.85 }}
            />
          </div>
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
            candidates={nightTargets ?? aliveCharacters.filter(c => c !== characterName)}
            onAction={handleNightAction}
          />
        )}

        {/* Night: submitted confirmation */}
        {phase === 'night' && !isEliminated && nightActionSubmitted && ROLE_INFO[role]?.action && (
          <div className="container" style={{ paddingTop: 12, textAlign: 'center' }}>
            <p style={{ color: 'var(--success)', fontSize: '0.875rem' }}>
              ✓ {nightActionTarget ? `You targeted ${nightActionTarget}.` : 'Your action has been submitted.'} Rest now…
            </p>
            <div style={{ marginTop: 8 }}>
              <div className="pulse-glow" style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', margin: '0 auto 6px' }} />
              <p style={{ color: 'var(--text-dim)', fontSize: '0.75rem' }}>Waiting for other players…</p>
            </div>
          </div>
        )}

        {/* Night: villager / hunter (no action) */}
        {phase === 'night' && !isEliminated && !ROLE_INFO[role]?.action && (
          <div className="container" style={{ paddingTop: 12, textAlign: 'center' }}>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>
              🌙 The village sleeps…
            </p>
            <div style={{ marginTop: 8 }}>
              <div className="pulse-glow" style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent)', margin: '0 auto 6px' }} />
              <p style={{ color: 'var(--text-dim)', fontSize: '0.75rem' }}>Waiting for special roles…</p>
            </div>
          </div>
        )}

        {/* Eliminated spectator — clue panel during discussion + voting */}
        {isEliminated && !hunterRevengeNeeded && (phase === 'day_discussion' || phase === 'day_vote') && (
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
            myCharacterName={characterName}
            aiCharacter={aiCharacter}
          />
        )}

        {/* Day-phase hint — one-time contextual tip for first-timers (§ UX-day-hint) */}
        {phase === 'day_discussion' && !isEliminated && !dayHintDismissed && (
          <div
            className="container"
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '8px 16px',
              background: 'var(--bg-elevated)',
              borderTop: '1px solid var(--border)',
              gap: 8,
            }}
          >
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
              💬 Speak naturally — tap a reaction to highlight your point
            </span>
            <button
              onClick={() => {
                localStorage.setItem('dayHintSeen', '1')
                setDayHintDismissed(true)
              }}
              aria-label="Dismiss hint"
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--text-dim)',
                cursor: 'pointer',
                fontSize: '0.875rem',
                padding: '4px 6px',
                flexShrink: 0,
              }}
            >
              ✕
            </button>
          </div>
        )}

        {/* Chat bar + quick reactions */}
        {showChat && (
          <>
            {/* Mic status bar */}
            <div className="container" style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 16px' }}>
              <button
                onClick={toggleMute}
                style={{
                  background: muted ? 'var(--danger-dim, #3a1c1c)' : 'var(--bg-elevated)',
                  border: `1px solid ${muted ? 'var(--danger)' : 'var(--border-accent, var(--border))'}`,
                  borderRadius: 'var(--radius-full, 999px)',
                  padding: '6px 12px',
                  color: 'var(--text)',
                  cursor: 'pointer',
                  fontSize: '0.8125rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
                title={muted ? 'Unmute microphone' : 'Mute microphone'}
              >
                {muted ? '\uD83D\uDD07' : '\uD83C\uDFA4'}
                <span>{muted ? 'Muted' : 'Mic On'}</span>
              </button>
              {micError && (
                <span style={{ fontSize: '0.75rem', color: 'var(--danger)' }}>{micError}</span>
              )}
              {micActive && !muted && (
                <span style={{ fontSize: '0.75rem', color: 'var(--success)' }}>
                  <span className="pulse-glow" style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'var(--success)', marginRight: 4 }} />
                  Narrator can hear you
                </span>
              )}
            </div>
            <ChatBar
              chatText={chatText}
              onChange={setChatText}
              onSubmit={handleChat}
              isConnected={connectionStatus === 'connected'}
            />
            <QuickReactionBar
              key={round}
              aliveCharacters={aliveCharacters}
              myCharacterName={characterName}
              onReaction={handleQuickReaction}
              onRaiseHand={handleRaiseHand}
              handRaised={handRaised}
            />
          </>
        )}
      </div>

      {/* ── Role strip (sticky bottom drawer, §12.3.6) ── */}
      {role && phase !== 'setup' && phase !== 'game_over' && (
        <RoleStrip role={role} characterName={characterName} />
      )}
    </div>
  )
}
