import { useState } from 'react'
import { useNavigate, useSearchParams, useParams } from 'react-router-dom'
import { useGame } from '../../context/GameContext.jsx'

const DIFF_DESC = {
  easy:   'Shapeshifter plays cautiously — easier to spot.',
  normal: 'Balanced challenge for most groups.',
  hard:   'The Shapeshifter is cunning. Good luck.',
}

export default function JoinLobby() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { gameCode: urlGameCode } = useParams()
  const { dispatch } = useGame()

  const isHost = searchParams.get('host') === 'true'
  const [name, setName] = useState('')
  const [gameCode, setGameCode] = useState(urlGameCode ?? '')
  const [difficulty, setDifficulty] = useState('normal')
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    const trimmedName = name.trim()
    if (!trimmedName) return setError('Please enter your name.')
    if (!isHost && !gameCode.trim()) return setError('Please enter a game code.')
    setLoading(true)
    setError(null)
    try {
      let gameId, playerId
      if (isHost) {
        const res = await fetch('/api/games', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ host_name: trimmedName, difficulty }),
        })
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body.detail ?? 'Failed to create game')
        }
        const data = await res.json()
        gameId = data.game_id
        playerId = data.host_player_id
      } else {
        const code = gameCode.trim().toUpperCase()
        const res = await fetch(`/api/games/${code}/join`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ player_name: trimmedName }),
        })
        if (!res.ok) {
          const body = await res.json().catch(() => ({}))
          throw new Error(body.detail ?? 'Game not found or already started')
        }
        const data = await res.json()
        gameId = data.game_id
        playerId = data.player_id
      }
      dispatch({ type: 'SET_PLAYER', playerId, playerName: trimmedName, isHost })
      dispatch({ type: 'SET_GAME', gameId, difficulty })
      navigate(`/game/${gameId}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page" style={{ justifyContent: 'center', padding: '40px 16px' }}>
      <div className="container">
        <button
          className="btn btn-ghost btn-sm"
          style={{ marginBottom: 24 }}
          onClick={() => navigate('/')}
        >
          ← Back
        </button>

        <h2 style={{ marginBottom: 4 }}>
          {isHost ? '🔥 Create Game' : 'Join Thornwood'}
        </h2>
        <p style={{ marginBottom: 28 }}>
          {isHost
            ? 'Summon a new gathering in the village.'
            : 'Enter your name and the game code to join your village.'}
        </p>

        <form
          onSubmit={handleSubmit}
          style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
        >
          {/* Name */}
          <div>
            <label className="input-label">Your Name</label>
            <input
              className="input"
              placeholder="Enter your name"
              value={name}
              onChange={e => setName(e.target.value)}
              maxLength={24}
              autoFocus
              autoComplete="off"
            />
          </div>

          {/* Game code (join only) */}
          {!isHost && (
            <div>
              <label className="input-label">Game Code</label>
              <input
                className="input"
                placeholder="e.g. ABC12345"
                value={gameCode}
                onChange={e => setGameCode(e.target.value.toUpperCase())}
                style={{ letterSpacing: '0.12em', fontFamily: 'var(--font-heading)' }}
                autoComplete="off"
              />
            </div>
          )}

          {/* Difficulty (host only) */}
          {isHost && (
            <div>
              <label className="input-label">Difficulty</label>
              <div style={{ display: 'flex', gap: 8, marginBottom: 6 }}>
                {['easy', 'normal', 'hard'].map(d => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDifficulty(d)}
                    className={`btn btn-sm ${difficulty === d ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ flex: 1 }}
                  >
                    {d.charAt(0).toUpperCase() + d.slice(1)}
                  </button>
                ))}
              </div>
              <p style={{ fontSize: '0.75rem' }}>{DIFF_DESC[difficulty]}</p>
            </div>
          )}

          {error && (
            <p style={{ color: 'var(--danger)', fontSize: '0.875rem', margin: 0 }}>{error}</p>
          )}

          <button type="submit" className="btn btn-primary btn-lg" disabled={loading}>
            {loading ? 'Connecting…' : isHost ? '🔥 Create Game' : 'Join Game'}
          </button>

          <p style={{ textAlign: 'center', fontSize: '0.875rem', marginTop: 4 }}>
            {isHost ? (
              <>Have a code?{' '}
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ display: 'inline', padding: '0 4px' }}
                  onClick={() => navigate('/join')}
                >
                  Join instead
                </button>
              </>
            ) : (
              <>Want to host?{' '}
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ display: 'inline', padding: '0 4px' }}
                  onClick={() => navigate('/join?host=true')}
                >
                  Create a game
                </button>
              </>
            )}
          </p>
        </form>
      </div>
    </div>
  )
}
