import { useState } from 'react'
import { useNavigate, useSearchParams, useParams } from 'react-router-dom'
import { useGame } from '../../context/GameContext.jsx'

const DIFF_DESC = {
  easy:   'Shapeshifter plays cautiously — easier to spot.',
  normal: 'Balanced challenge for most groups.',
  hard:   'The Shapeshifter is cunning. Good luck.',
}

const PRESETS = [
  { id: 'classic',  label: '⚔️ Classic',  desc: 'Deep, dramatic fantasy narrator' },
  { id: 'campfire', label: '🔥 Campfire', desc: 'Warm storyteller among friends' },
  { id: 'horror',   label: '🕯️ Horror',   desc: 'Slow, unsettling dread' },
  { id: 'comedy',   label: '😏 Comedy',   desc: 'Wry, self-aware humor' },
]

export default function JoinLobby() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { gameCode: urlGameCode } = useParams()
  const { dispatch } = useGame()

  const isHost = searchParams.get('host') === 'true'
  const [name, setName] = useState('')
  const [gameCode, setGameCode] = useState(urlGameCode ?? '')
  const [difficulty, setDifficulty] = useState('normal')
  const [randomAlignment, setRandomAlignment] = useState(false)
  const [narratorPreset, setNarratorPreset] = useState('classic')
  const [inPersonMode, setInPersonMode] = useState(false)
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
          body: JSON.stringify({ host_name: trimmedName, difficulty, random_alignment: randomAlignment, narrator_preset: narratorPreset, in_person_mode: inPersonMode }),
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

          {/* Random Alignment (host only) §12.3.10 */}
          {isHost && (
            <div>
              <label className="input-label">AI Alignment</label>
              <button
                type="button"
                onClick={() => setRandomAlignment(v => !v)}
                className={`btn btn-sm ${randomAlignment ? 'btn-primary' : 'btn-ghost'}`}
                style={{ width: '100%', justifyContent: 'flex-start', gap: 10 }}
              >
                <span>{randomAlignment ? '🎲' : '🐺'}</span>
                {randomAlignment ? 'Random — AI may be loyal or traitor' : 'Classic — AI is always the Shapeshifter'}
              </button>
              <p style={{ fontSize: '0.75rem', marginTop: 6 }}>
                {randomAlignment
                  ? 'There is a chance the AI is on the village\'s side. Can you tell?'
                  : 'The AI is always the Shapeshifter. Find and vote it out.'}
              </p>
            </div>
          )}

          {/* Narrator Style (host only) §12.3.17 */}
          {isHost && (
            <div>
              <label className="input-label">Narrator Style</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 6 }}>
                {PRESETS.map(p => (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setNarratorPreset(p.id)}
                    className={`btn btn-sm ${narratorPreset === p.id ? 'btn-primary' : 'btn-ghost'}`}
                    style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 2, padding: '8px 10px', height: 'auto' }}
                  >
                    <span>{p.label}</span>
                    <span style={{ fontSize: '0.6875rem', color: narratorPreset === p.id ? 'rgba(255,255,255,0.75)' : 'var(--text-dim)', fontWeight: 400 }}>
                      {p.desc}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* In-Person Mode (host only) §12.3.16 */}
          {isHost && (
            <div>
              <label className="input-label">Vote Mode</label>
              <button
                type="button"
                onClick={() => setInPersonMode(v => !v)}
                className={`btn btn-sm ${inPersonMode ? 'btn-primary' : 'btn-ghost'}`}
                style={{ width: '100%', justifyContent: 'flex-start', gap: 10 }}
              >
                <span>{inPersonMode ? '🎥' : '📱'}</span>
                {inPersonMode ? 'In-Person — camera counts raised hands' : 'Phone — tap to vote on your device'}
              </button>
              <p style={{ fontSize: '0.75rem', marginTop: 6 }}>
                {inPersonMode
                  ? 'During votes, the narrator will use the camera to count raised hands.'
                  : 'Each player taps their phone to submit a vote.'}
              </p>
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
