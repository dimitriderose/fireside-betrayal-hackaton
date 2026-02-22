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
const EVENT_RENDERERS = {
  night_target: (e) => ({
    icon: '🎯',
    text: `${e.actor} chose to eliminate ${e.target}.`,
    hidden: true,
  }),
  night_kill_attempt: (e) => ({
    icon: e.data?.blocked ? '🛡️' : '🗡️',
    text: e.data?.blocked
      ? `${e.actor} attacked ${e.target} — but the Healer intervened.`
      : `${e.actor} eliminated ${e.target}.`,
    hidden: true,
  }),
  night_heal: (e) => ({
    icon: '💚',
    text: `${e.actor} protected ${e.target} through the night.`,
    hidden: true,
  }),
  night_investigation: (e) => ({
    icon: e.data?.is_drunk ? '🍺' : '🔮',
    text: e.data?.is_drunk
      ? `${e.actor} investigated ${e.target} (received wrong result — they are Drunk).`
      : `${e.actor} investigated ${e.target}: ${e.data?.result ? 'IS the Shapeshifter' : 'is NOT the Shapeshifter'}.`,
    hidden: true,
  }),
  elimination: (e) => ({
    icon: '⚰️',
    text: e.data?.was_traitor
      ? `${e.target} was eliminated — the Shapeshifter unmasked!`
      : `${e.target} was eliminated (${e.data?.role ?? 'villager'}).`,
    hidden: false,
  }),
  hunter_revenge: (e) => ({
    icon: '🏹',
    text: `${e.actor} took ${e.target} with them as their dying act.`,
    hidden: false,
  }),
}

function TimelineRound({ roundEntry }) {
  const { round, events } = roundEntry
  if (!events?.length) return null

  return (
    <div style={{ marginBottom: 20 }}>
      <div
        style={{
          fontSize: '0.6875rem',
          color: 'var(--text-muted)',
          textTransform: 'uppercase',
          letterSpacing: '0.12em',
          marginBottom: 10,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
        }}
      >
        <span
          style={{
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-full)',
            padding: '2px 10px',
          }}
        >
          Round {round}
        </span>
        <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {events.map((ev, i) => {
          const renderer = EVENT_RENDERERS[ev.type]
          if (!renderer) return null
          const rendered = renderer(ev)
          return (
            <div
              key={i}
              style={{
                display: 'flex',
                gap: 10,
                alignItems: 'flex-start',
                padding: '8px 10px',
                background: rendered.hidden ? 'rgba(255,107,53,0.05)' : 'var(--bg-card)',
                border: `1px solid ${rendered.hidden ? 'var(--border-accent)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-md)',
                opacity: 0.92,
              }}
              className="fade-in"
            >
              <span style={{ fontSize: '1rem', flexShrink: 0 }}>{rendered.icon}</span>
              <div>
                <p style={{ fontSize: '0.8125rem', lineHeight: 1.5, margin: 0, color: 'var(--text)' }}>
                  {rendered.text}
                </p>
                {rendered.hidden && (
                  <span
                    style={{
                      fontSize: '0.6rem',
                      color: 'var(--accent)',
                      textTransform: 'uppercase',
                      letterSpacing: '0.08em',
                    }}
                  >
                    Hidden during game
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
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
                          {r.role?.charAt(0).toUpperCase() + r.role?.slice(1)}
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

        {/* Post-game reveal timeline */}
        {strategyLog.length > 0 && (
          <div style={{ marginBottom: 32 }}>
            <h3
              style={{
                marginBottom: 6,
                fontSize: '0.8125rem',
                color: 'var(--text-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
              }}
            >
              What Really Happened
            </h3>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: 16 }}>
              Every hidden action — now revealed.
            </p>
            {strategyLog.map((roundEntry, i) => (
              <TimelineRound key={i} roundEntry={roundEntry} />
            ))}
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
