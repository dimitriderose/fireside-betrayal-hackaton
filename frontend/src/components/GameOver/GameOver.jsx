import { useState } from 'react'
import { useNavigate, Navigate } from 'react-router-dom'
import { useGame } from '../../context/GameContext.jsx'

const ROLE_ICONS = {
  villager: '🧑‍🌾',
  seer: '🔮',
  healer: '💚',
  hunter: '🏹',
  drunk: '🍺',
  shapeshifter: '🐺',
}

// Timeline event type → { icon, label(actor, target, data) }
// night_target is intentionally omitted — night_kill_attempt already covers the same action
const EVENT_RENDERERS = {
  night_kill_attempt: (e) => ({
    icon: e.data?.blocked ? '🛡️' : '🗡️',
    text: e.data?.blocked
      ? `${e.actor ?? 'Unknown'} attacked ${e.target ?? 'Unknown'} — but the Healer intervened.`
      : `${e.actor ?? 'Unknown'} eliminated ${e.target ?? 'Unknown'}.`,
    hidden: true,
  }),
  night_heal: (e) => ({
    icon: '💚',
    text: `${e.actor ?? 'Unknown'} protected ${e.target ?? 'Unknown'} through the night.`,
    hidden: true,
  }),
  night_investigation: (e) => ({
    icon: e.data?.is_drunk ? '🍺' : '🔮',
    text: e.data?.is_drunk
      ? `${e.actor ?? 'Unknown'} investigated ${e.target ?? 'Unknown'} (received wrong result — they are Drunk).`
      : `${e.actor ?? 'Unknown'} investigated ${e.target ?? 'Unknown'}: ${e.data?.result ? 'IS the Shapeshifter' : 'is NOT the Shapeshifter'}.`,
    hidden: true,
  }),
  elimination: (e) => ({
    icon: '⚰️',
    text: e.data?.was_traitor
      ? `${e.target ?? 'Unknown'} was eliminated — the Shapeshifter unmasked!`
      : `${e.target ?? 'Unknown'} was eliminated (${e.data?.role ?? 'villager'}).`,
    hidden: false,
  }),
  hunter_revenge: (e) => ({
    icon: '🏹',
    text: `${e.actor ?? 'Unknown'} took ${e.target ?? 'Unknown'} with them as their dying act.`,
    hidden: false,
  }),
}

// ── InteractiveTimeline (§12.3.13) ─────────────────────────────────────────────

function EventCard({ ev, index }) {
  const renderer = EVENT_RENDERERS[ev.type]
  if (!renderer) return null
  const rendered = renderer(ev)
  return (
    <div
      key={ev.id ?? `${ev.type}-${ev.actor}-${ev.target}-${index}`}
      style={{
        display: 'flex',
        gap: 10,
        alignItems: 'flex-start',
        padding: '8px 10px',
        background: rendered.hidden ? 'rgba(220,38,38,0.05)' : 'var(--bg-card)',
        border: `1px solid ${rendered.hidden ? 'rgba(220,38,38,0.3)' : 'var(--border)'}`,
        borderRadius: 'var(--radius-md)',
        opacity: 0.92,
        marginBottom: 6,
      }}
      className="fade-in"
    >
      <span style={{ fontSize: '1rem', flexShrink: 0 }}>{rendered.icon}</span>
      <div>
        <p style={{ fontSize: '0.8125rem', lineHeight: 1.5, margin: 0, color: 'var(--text)' }}>
          {rendered.text}
        </p>
        {rendered.hidden && (
          <span style={{ fontSize: '0.6875rem', color: 'var(--danger)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Secret
          </span>
        )}
      </div>
    </div>
  )
}

function InteractiveTimeline({ rounds }) {
  const [view, setView] = useState('split')          // 'public' | 'secret' | 'split'
  const [selectedRound, setSelectedRound] = useState(null)  // null = all rounds

  if (!rounds?.length) return null

  // Determine key moment: round where AI was closest to being caught.
  // Heuristic: round with the most secret events (hidden night actions reveal AI activity).
  const keyRound = rounds.reduce((best, r) => {
    const secretCount = (r.events ?? []).filter(e => !e.visible).length
    const bestCount = (best?.events ?? []).filter(e => !e.visible).length
    return secretCount >= bestCount ? r : best
  }, null)?.round

  const visibleRounds = selectedRound
    ? rounds.filter(r => r.round === selectedRound)
    : rounds

  return (
    <div>
      {/* ── View Toggle ── */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 16, flexWrap: 'wrap' }}>
        {[['public', '☀ Public'], ['secret', '🔴 Secret'], ['split', '◫ Split']].map(([v, label]) => (
          <button
            key={v}
            onClick={() => setView(v)}
            style={{
              padding: '5px 14px',
              fontSize: '0.75rem',
              borderRadius: 'var(--radius-full)',
              border: `1px solid ${view === v ? 'var(--border-accent)' : 'var(--border)'}`,
              background: view === v ? 'var(--accent-glow)' : 'var(--bg-elevated)',
              color: view === v ? 'var(--accent)' : 'var(--text-muted)',
              cursor: 'pointer',
              fontFamily: 'var(--font-heading)',
              letterSpacing: '0.05em',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Round Scrubber ── */}
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.6875rem', color: 'var(--text-dim)', marginRight: 4 }}>Rounds:</span>
        <button
          onClick={() => setSelectedRound(null)}
          style={{
            padding: '3px 10px',
            fontSize: '0.6875rem',
            borderRadius: 'var(--radius-full)',
            border: `1px solid ${selectedRound === null ? 'var(--border-accent)' : 'var(--border)'}`,
            background: selectedRound === null ? 'var(--accent-glow)' : 'var(--bg-elevated)',
            color: selectedRound === null ? 'var(--accent)' : 'var(--text-muted)',
            cursor: 'pointer',
          }}
        >
          All
        </button>
        {rounds.map(r => (
          <button
            key={r.round}
            onClick={() => setSelectedRound(r.round === selectedRound ? null : r.round)}
            title={r.round === keyRound ? 'Key moment — AI was closest to being caught' : `Round ${r.round}`}
            style={{
              padding: '3px 10px',
              fontSize: '0.6875rem',
              borderRadius: 'var(--radius-full)',
              border: `1px solid ${selectedRound === r.round ? 'var(--border-accent)' : r.round === keyRound ? 'var(--danger)' : 'var(--border)'}`,
              background: selectedRound === r.round ? 'var(--accent-glow)' : 'var(--bg-elevated)',
              color: selectedRound === r.round ? 'var(--accent)' : r.round === keyRound ? 'var(--danger)' : 'var(--text-muted)',
              cursor: 'pointer',
              animation: r.round === keyRound && selectedRound === null ? 'pulse-border 2s infinite' : 'none',
            }}
          >
            {r.round}{r.round === keyRound ? ' ★' : ''}
          </button>
        ))}
      </div>

      {/* ── Timeline content ── */}
      {visibleRounds.map(roundEntry => {
        const { round, events = [] } = roundEntry
        const publicEvents = events.filter(e => e.visible)
        const secretEvents = events.filter(e => !e.visible)
        const isKeyRound = round === keyRound

        return (
          <div
            key={round}
            style={{
              marginBottom: 24,
              border: isKeyRound ? '1px solid rgba(220,38,38,0.4)' : '1px solid transparent',
              borderRadius: 'var(--radius-md)',
              padding: isKeyRound ? 12 : 0,
              transition: 'border-color 0.3s',
            }}
          >
            {/* Round header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <span style={{
                background: 'var(--bg-elevated)',
                border: `1px solid ${isKeyRound ? 'rgba(220,38,38,0.4)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-full)',
                padding: '2px 10px',
                fontSize: '0.6875rem',
                color: isKeyRound ? 'var(--danger)' : 'var(--text-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.12em',
              }}>
                Round {round}{isKeyRound ? ' — Key Moment ★' : ''}
              </span>
              <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
            </div>

            {/* Split view */}
            {view === 'split' && (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                <div>
                  <div style={{ fontSize: '0.625rem', color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
                    ☀ Public
                  </div>
                  {publicEvents.length === 0
                    ? <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>No public events</p>
                    : publicEvents.map((ev, i) => <EventCard key={i} ev={ev} index={i} />)
                  }
                </div>
                <div style={{ borderLeft: '2px solid rgba(220,38,38,0.25)', paddingLeft: 10 }}>
                  <div style={{ fontSize: '0.625rem', color: 'var(--danger)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>
                    🔴 Secret
                  </div>
                  {secretEvents.length === 0
                    ? <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>No secret actions</p>
                    : secretEvents.map((ev, i) => <EventCard key={i} ev={ev} index={i} />)
                  }
                </div>
              </div>
            )}

            {/* Public-only view */}
            {view === 'public' && (
              publicEvents.length === 0
                ? <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>No public events this round</p>
                : publicEvents.map((ev, i) => <EventCard key={i} ev={ev} index={i} />)
            )}

            {/* Secret-only view */}
            {view === 'secret' && (
              secretEvents.length === 0
                ? <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>No secret actions this round</p>
                : secretEvents.map((ev, i) => <EventCard key={i} ev={ev} index={i} />)
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function GameOver() {
  const navigate = useNavigate()
  const { state, dispatch } = useGame()
  const { winner, reveals, strategyLog, characterName: myCharacterName } = state

  // Guard against direct URL navigation or page refresh (no game state in context)
  if (!winner) return <Navigate to="/" replace />

  const handlePlayAgain = () => {
    dispatch({ type: 'RESET' })
    navigate('/')
  }

  const villagersWon = winner === 'villagers'

  return (
    <div className="page">
      {/* Hero */}
      <div
        style={{
          background: villagersWon
            ? 'linear-gradient(180deg, rgba(22,163,74,0.15) 0%, transparent 100%)'
            : 'linear-gradient(180deg, rgba(220,38,38,0.15) 0%, transparent 100%)',
          paddingTop: 48,
          paddingBottom: 32,
          textAlign: 'center',
        }}
      >
        <div style={{ fontSize: '3.5rem', marginBottom: 12 }}>
          {villagersWon ? '🌅' : '🐺'}
        </div>
        <h1
          style={{
            fontFamily: 'var(--font-heading)',
            fontSize: '1.75rem',
            color: villagersWon ? 'var(--success)' : 'var(--danger)',
            marginBottom: 8,
          }}
        >
          {villagersWon ? 'The Village Triumphs' : 'The Shapeshifter Wins'}
        </h1>
        <p style={{ fontSize: '0.9375rem', fontStyle: 'italic', color: 'var(--text-muted)' }}>
          {villagersWon
            ? 'The darkness is lifted from Thornwood.'
            : 'Thornwood falls to shadow and deception.'}
        </p>
      </div>

      <div className="container" style={{ paddingBottom: 40 }}>

        {/* Character Reveals */}
        {reveals.length > 0 && (
          <div style={{ marginBottom: 32 }}>
            <h3 style={{ marginBottom: 16, fontSize: '0.8125rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
              True Identities Revealed
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {reveals.map((r) => {
                const isMe = r.characterName === myCharacterName
                const isTraitor = r.role === 'shapeshifter'
                return (
                  <div
                    key={r.characterName}
                    className="card fade-in"
                    style={{
                      border: `1px solid ${isTraitor ? 'var(--danger)' : isMe ? 'var(--border-accent)' : 'var(--border)'}`,
                      padding: '12px 16px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ fontSize: '1.5rem' }}>
                          {ROLE_ICONS[r.role] ?? '❓'}
                        </span>
                        <div>
                          <div
                            style={{
                              fontWeight: 600,
                              fontSize: '0.9375rem',
                              color: isTraitor ? 'var(--danger)' : 'var(--text)',
                            }}
                          >
                            {r.characterName}
                          </div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            {r.playerName}
                          </div>
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <span
                          className={`badge ${isTraitor ? 'badge-danger' : 'badge-muted'}`}
                          style={{ fontSize: '0.625rem' }}
                        >
                          {r.role ? r.role.charAt(0).toUpperCase() + r.role.slice(1) : '?'}
                        </span>
                        {isMe && (
                          <div
                            style={{ fontSize: '0.625rem', color: 'var(--accent)', marginTop: 4 }}
                          >
                            You
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* No reveals yet */}
        {reveals.length === 0 && (
          <div style={{ textAlign: 'center', paddingTop: 16, paddingBottom: 24 }}>
            <p style={{ color: 'var(--text-dim)' }}>The village's secrets remain…</p>
          </div>
        )}

        {/* Post-game interactive timeline (§12.3.13) */}
        {strategyLog.length > 0 && (
          <div style={{ marginBottom: 32 }}>
            <h3
              style={{
                marginBottom: 4,
                fontSize: '0.8125rem',
                color: 'var(--text-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
              }}
            >
              What Really Happened
            </h3>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: 16 }}>
              Toggle between public and secret views. The ★ round is where the AI was closest to being caught.
            </p>
            <InteractiveTimeline rounds={strategyLog} />
          </div>
        )}

        {/* Play Again */}
        <button className="btn btn-primary btn-lg" onClick={handlePlayAgain}>
          🔥 Play Again
        </button>
      </div>
    </div>
  )
}
