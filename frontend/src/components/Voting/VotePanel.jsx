import { useState, useEffect, useRef } from 'react'
import { useGame } from '../../context/GameContext.jsx'

const VOTE_TIMER_SECONDS = 60

/**
 * VotePanel — rendered during the day_vote phase only.
 *
 * Normal mode: shows one vote button per alive character (human players + AI).
 * In-Person mode (§12.3.16): host captures camera frames; Gemini counts hands.
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
    isHost,
    inPersonMode,
    voteCandidates,  // string[] | null — backend-filtered list excluding self
  } = state

  const [timeLeft, setTimeLeft] = useState(VOTE_TIMER_SECONDS)
  // Camera state (in-person mode only)
  const videoRef = useRef(null)
  const [cameraActive, setCameraActive] = useState(false)
  const [cameraError, setCameraError] = useState(null)
  const [captureLoading, setCaptureLoading] = useState(null) // candidate name being captured
  const [cameraResults, setCameraResults] = useState({})    // { charName: handCount }
  const [fallbackMode, setFallbackMode] = useState(false)

  // Reset and start countdown whenever the day_vote phase begins (new round)
  useEffect(() => {
    if (phase !== 'day_vote') return
    setTimeLeft(VOTE_TIMER_SECONDS)
    const interval = setInterval(() => {
      setTimeLeft(prev => (prev > 0 ? prev - 1 : 0))
    }, 1000)
    return () => clearInterval(interval)
  }, [phase, round])

  // Camera: activate when in-person mode + host + day_vote
  useEffect(() => {
    if (!inPersonMode || !isHost || phase !== 'day_vote') return
    let stream = null
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: 'environment' } })
      .then(s => {
        stream = s
        if (videoRef.current) videoRef.current.srcObject = s
        setCameraActive(true)
        setCameraError(null)
      })
      .catch(() => {
        setCameraError('Camera unavailable — using phone voting instead.')
        setFallbackMode(true)
      })
    return () => {
      stream?.getTracks().forEach(t => t.stop())
      setCameraActive(false)
    }
  }, [inPersonMode, isHost, phase, round])

  // Listen for camera vote results and fallbacks from server
  useEffect(() => {
    const onResult = (e) => {
      setCameraResults(prev => ({ ...prev, [e.detail.characterName]: e.detail.handCount }))
      setCaptureLoading(null)
    }
    const onFallback = () => {
      setFallbackMode(true)
      setCaptureLoading(null)
    }
    window.addEventListener('camera-vote-result', onResult)
    window.addEventListener('camera-vote-fallback', onFallback)
    return () => {
      window.removeEventListener('camera-vote-result', onResult)
      window.removeEventListener('camera-vote-fallback', onFallback)
    }
  }, [])

  const handleCameraCapture = (charName) => {
    if (!videoRef.current || captureLoading) return
    const canvas = document.createElement('canvas')
    canvas.width = videoRef.current.videoWidth || 640
    canvas.height = videoRef.current.videoHeight || 480
    canvas.getContext('2d').drawImage(videoRef.current, 0, 0)
    const imageData = canvas.toDataURL('image/jpeg', 0.8).split(',')[1]
    setCaptureLoading(charName)
    sendMessage('in_person_vote_frame', { characterName: charName, imageData })
  }

  // Delay showing the vote panel: wait for BOTH a minimum 3s delay (narrator transition)
  // AND backend candidates to arrive. This prevents showing an empty/wrong candidate list.
  const [timerDone, setTimerDone] = useState(false)
  useEffect(() => {
    if (phase === 'day_vote') {
      setTimerDone(false)
      const timer = setTimeout(() => setTimerDone(true), 3000)
      return () => clearTimeout(timer)
    }
    setTimerDone(false)
  }, [phase, round])

  // Use backend-provided candidate list (excludes self). Fall back to local filter.
  const fallbackCandidates = [
    ...players.filter(p => p.alive && p.characterName !== myCharacterName).map(p => p.characterName),
    ...(aiCharacter?.alive ? [aiCharacter.name] : []),
  ]
  const candidates = voteCandidates ?? fallbackCandidates
  const hasCandidates = candidates.length > 0

  if (phase !== 'day_vote') return null
  if (!timerDone || !hasCandidates) {
    const waitMsg = !timerDone
      ? 'The narrator calls for a vote…'
      : 'Gathering the village…'
    return (
      <div className="container" style={{ paddingTop: 32, textAlign: 'center' }}>
        <div className="pulse-glow" style={{ width: 12, height: 12, borderRadius: '50%', background: 'var(--accent)', margin: '0 auto 12px' }} />
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem' }}>{waitMsg}</p>
      </div>
    )
  }

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
            : inPersonMode && !fallbackMode
              ? isHost
                ? 'Capture a photo for each candidate when hands are raised.'
                : 'The host is counting raised hands with the camera.'
              : myVote
                ? `You cast your vote against ${myVote}.`
                : 'Who is the Shapeshifter? Cast your vote to eliminate a suspect.'}
        </p>

        {/* ── In-Person Camera UI (§12.3.16, host only) ── */}
        {inPersonMode && isHost && !fallbackMode && !isEliminated && (
          <div style={{ marginBottom: 16 }}>
            {cameraError && (
              <p style={{ fontSize: '0.8125rem', color: 'var(--danger)', marginBottom: 8 }}>{cameraError}</p>
            )}
            {/* Camera preview */}
            <div style={{ borderRadius: 'var(--radius-md)', overflow: 'hidden', marginBottom: 12, background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}>
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                style={{ width: '100%', display: 'block', maxHeight: 200, objectFit: 'cover' }}
              />
              {!cameraActive && (
                <div style={{ padding: 16, textAlign: 'center', color: 'var(--text-dim)', fontSize: '0.8125rem' }}>
                  🎥 Camera starting…
                </div>
              )}
            </div>
            {/* Per-candidate capture buttons */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {candidates.map(charName => {
                const count = cameraResults[charName]
                const isCapturing = captureLoading === charName
                return (
                  <button
                    key={charName}
                    className="btn btn-ghost"
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px' }}
                    disabled={!!captureLoading || !cameraActive}
                    onClick={() => handleCameraCapture(charName)}
                  >
                    <span style={{ fontWeight: 600 }}>{charName}</span>
                    <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
                      {isCapturing ? '📸 Counting…' : count !== undefined ? `🖐 ${count} hand${count !== 1 ? 's' : ''}` : '📸 Capture'}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* ── In-Person: non-host watching message ── */}
        {inPersonMode && !isHost && !fallbackMode && !isEliminated && (
          <div style={{ textAlign: 'center', padding: '12px 0', color: 'var(--text-muted)' }}>
            <div className="pulse-glow" style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--accent)', margin: '0 auto 10px' }} />
            The host is counting votes with the camera…
          </div>
        )}

        {/* ── Vote Buttons (normal mode OR fallback) ── */}
        {(!inPersonMode || fallbackMode) && !isEliminated && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {candidates.map(charName => {
              const isSelected = myVote === charName
              const count = votes[charName] ?? 0

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

        {/* ── Eliminated player view — read-only tally ── */}
        {isEliminated && (
          <>
            <div style={{ textAlign: 'center', padding: '12px 0 8px', color: 'var(--text-dim)' }}>
              <div style={{ fontSize: '1.5rem', marginBottom: 4 }}>🕯</div>
              <p style={{ fontSize: '0.8125rem' }}>You watch the vote unfold from beyond...</p>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {candidates.map(charName => {
                const count = votes[charName] ?? 0
                return (
                  <div
                    key={charName}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 14px',
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border)',
                      borderRadius: 'var(--radius-md)',
                      opacity: 0.7,
                    }}
                  >
                    <span style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text-muted)' }}>{charName}</span>
                    <span
                      style={{
                        fontFamily: 'var(--font-heading)',
                        fontSize: '1rem',
                        fontWeight: 700,
                        color: count > 0 ? 'var(--danger)' : 'var(--text-dim)',
                        minWidth: 24,
                        textAlign: 'right',
                      }}
                    >
                      {count > 0 ? count : '—'}
                    </span>
                  </div>
                )
              })}
            </div>
          </>
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
