import { useState, useEffect } from 'react'
import { useGame } from '../../context/GameContext.jsx'

const VOTE_TIMER_SECONDS = 60

/**
 * VotePanel — rendered during the day_vote phase only.
 *
 * Shows one vote button per alive character (human players + AI character).
 * Once a vote is cast, buttons are disabled and the live tally animates in.
 * A 60-second countdown resets on each new round's day_vote phase.
 *
 * Props:
 *   sendMessage(type, data) — from useWebSocket, sends { type, data } to backend
 */
export default function VotePanel({ sendMessage }) {
  const { state, dispatch } = useGame()
  const {
    players,
    aiCharacter,
    votes,      // { charName: count } — live tally
    voteMap,    // { charName: votedFor | null } — who has voted (targets hidden)
    myVote,     // charName this player voted for, or null
    phase,
    round,
    characterName: myCharacterName,
    isEliminated,
  } = state

  const [timeLeft, setTimeLeft] = useState(VOTE_TIMER_SECONDS)

  // Reset and start countdown whenever the day_vote phase begins (new round)
  useEffect(() => {
    if (phase !== 'day_vote') return
    setTimeLeft(VOTE_TIMER_SECONDS)
    const interval = setInterval(() => {
      setTimeLeft(prev => (prev > 0 ? prev - 1 : 0))
    }, 1000)
    return () => clearInterval(interval)
  }, [phase, round])

  if (phase !== 'day_vote') return null

  // Build the candidate list: alive human characters + AI character (if alive)
  const aliveHumans = players.filter(p => p.alive).map(p => p.characterName)
  const aiName = aiCharacter?.alive ? aiCharacter.name : null
  const candidates = [...aliveHumans, ...(aiName ? [aiName] : [])]

  // How many human players have voted (from voteMap)
  const votedHumanCount = Object.entries(voteMap).filter(
    ([, votedFor]) => votedFor !== null
  ).length
  const totalHumanVoters = players.filter(p => p.alive).length
  const allVoted = totalHumanVoters > 0 && votedHumanCount >= totalHumanVoters

  const handleVote = (target) => {
    if (myVote || isEliminated) return
    dispatch({ type: 'SET_MY_VOTE', vote: target })
    sendMessage('vote', { target })
  }

  const timerColor = timeLeft <= 10
    ? 'var(--danger)'
    : timeLeft <= 20
      ? '#fbbf24'
      : 'var(--accent)'

  return (
    <div className="container">
      <div className="card fade-in" style={{ marginTop: 16 }}>

        {/* ── Header ── */}
        <div
          className="flex items-center justify-between"
          style={{ marginBottom: 16 }}
        >
          <div>
            <span className="phase-indicator phase-vote">⚖ Village Vote</span>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
              Round {round}
            </div>
          </div>

          {/* Countdown timer */}
          <div style={{ textAlign: 'center' }}>
            <div
              style={{
                fontFamily: 'var(--font-heading)',
                fontSize: '1.75rem',
                fontWeight: 700,
                color: timerColor,
                lineHeight: 1,
                transition: 'color 0.5s ease',
              }}
            >
              {timeLeft}
            </div>
            <div style={{ fontSize: '0.625rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
              seconds
            </div>
          </div>
        </div>

        {/* ── Instruction / Confirmation ── */}
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: 16 }}>
          {isEliminated
            ? 'You have been eliminated and cannot vote.'
            : myVote
              ? `You cast your vote against ${myVote}.`
              : 'Who is the Shapeshifter? Cast your vote to eliminate a suspect.'}
        </p>

        {/* ── Vote Buttons ── */}
        {!isEliminated && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {candidates.map(charName => {
              const isSelected = myVote === charName
              const isAI = aiName === charName
              const count = votes[charName] ?? 0
              const isSelf = charName === myCharacterName

              return (
                <button
                  key={charName}
                  onClick={() => handleVote(charName)}
                  disabled={!!myVote}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '14px 16px',
                    background: isSelected
                      ? 'linear-gradient(135deg, rgba(220,38,38,0.25), rgba(153,27,27,0.15))'
                      : 'var(--bg-elevated)',
                    border: `1px solid ${isSelected ? 'var(--danger)' : 'var(--border)'}`,
                    borderRadius: 'var(--radius-md)',
                    color: 'var(--text)',
                    textAlign: 'left',
                    cursor: myVote ? 'not-allowed' : 'pointer',
                    opacity: myVote && !isSelected ? 0.55 : 1,
                    transition: 'all var(--transition)',
                    outline: 'none',
                    width: '100%',
                  }}
                  onMouseEnter={e => {
                    if (!myVote) e.currentTarget.style.borderColor = 'rgba(220,38,38,0.5)'
                  }}
                  onMouseLeave={e => {
                    if (!myVote && !isSelected) e.currentTarget.style.borderColor = 'var(--border)'
                  }}
                >
                  {/* Character name + labels */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: '0.9375rem' }}>{charName}</span>
                    {isSelected && (
                      <span className="badge badge-danger" style={{ fontSize: '0.625rem' }}>
                        Your vote
                      </span>
                    )}
                    {isSelf && !isSelected && (
                      <span className="badge badge-muted" style={{ fontSize: '0.625rem' }}>
                        You
                      </span>
                    )}
                    {isAI && !isSelected && (
                      <span className="badge badge-muted" style={{ fontSize: '0.625rem' }}>
                        NPC
                      </span>
                    )}
                  </div>

                  {/* Live vote count */}
                  <span
                    style={{
                      fontFamily: 'var(--font-heading)',
                      fontSize: '1.125rem',
                      fontWeight: 700,
                      color: count > 0 ? 'var(--danger)' : 'var(--text-dim)',
                      minWidth: 28,
                      textAlign: 'right',
                    }}
                  >
                    {count > 0 ? count : '—'}
                  </span>
                </button>
              )
            })}
          </div>
        )}

        {/* ── Eliminated player view ── */}
        {isEliminated && (
          <div style={{ textAlign: 'center', padding: '16px 0', color: 'var(--text-dim)' }}>
            <div style={{ fontSize: '2rem', marginBottom: 8 }}>🕯</div>
            <p style={{ fontSize: '0.875rem' }}>You watch the vote unfold from beyond...</p>
          </div>
        )}

        {/* ── Vote Progress ── */}
        <div
          style={{
            marginTop: 20,
            paddingTop: 16,
            borderTop: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            {votedHumanCount} / {totalHumanVoters} villagers voted
          </span>
          {allVoted && (
            <span
              className="badge badge-danger pulse-glow"
              style={{ fontSize: '0.75rem' }}
            >
              Tallying votes…
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
