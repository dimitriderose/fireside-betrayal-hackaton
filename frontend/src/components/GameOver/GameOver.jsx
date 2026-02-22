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

export default function GameOver() {
  const navigate = useNavigate()
  const { state, dispatch } = useGame()
  const { winner, reveals, characterName: myCharacterName } = state

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

      <div className="container" style={{ paddingBottom: 32 }}>

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

        {/* No reveals yet (game may have ended before WS message) */}
        {reveals.length === 0 && (
          <div style={{ textAlign: 'center', paddingTop: 16, paddingBottom: 24 }}>
            <p style={{ color: 'var(--text-dim)' }}>The village's secrets remain…</p>
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
