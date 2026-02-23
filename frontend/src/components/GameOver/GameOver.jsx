import { useState, useRef, useEffect } from 'react'
import { useNavigate, Navigate } from 'react-router-dom'
import { useGame } from '../../context/GameContext.jsx'

function ShareButton({ winner, reveals }) {
  const [copied, setCopied] = useState(false)

  const handleShare = async () => {
    const loyalAIReveal = reveals.find(r => r.isAI && !r.isTraitor)
    const loyalAIVotedOut = winner === 'shapeshifter' && !!loyalAIReveal
    const outcome = winner === 'villagers'
      ? 'The Village Triumphs! 🌅'
      : loyalAIVotedOut
      ? 'We betrayed our ally! 🤝'
      : 'The Shapeshifter Wins! 🐺'
    const traitor = reveals.find(r => r.isTraitor ?? r.role === 'shapeshifter')
    const traitorLine = loyalAIReveal
      ? `The AI (${loyalAIReveal.characterName}) was loyal — on the village's side all along!`
      : traitor ? `The Shapeshifter was ${traitor.characterName} (${traitor.playerName}).` : ''
    const summary = `🔥 Fireside: Betrayal\n${outcome}\n${traitorLine}\nPlay at thornwood.app`

    if (navigator.share) {
      try {
        await navigator.share({ title: 'Fireside: Betrayal', text: summary })
        return
      } catch {
        // User cancelled or API not supported — fall through to clipboard
      }
    }

    try {
      await navigator.clipboard.writeText(summary)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch {
      // clipboard not available
    }
  }

  return (
    <button
      className="btn btn-ghost btn-lg"
      onClick={handleShare}
      style={{ marginLeft: 8 }}
    >
      {copied ? '✅ Copied!' : '📤 Share this game'}
    </button>
  )
}

const ROLE_ICONS = {
  villager: '🧑‍🌾',
  seer: '🔮',
  healer: '💚',
  hunter: '🏹',
  drunk: '🍺',
  shapeshifter: '🐺',
  bodyguard: '🛡️',
  tanner: '🪓',
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
  bodyguard_sacrifice: (e) => ({
    icon: '🛡️',
    text: `${e.actor ?? 'Unknown'} threw themselves in front of the attack, dying to protect ${e.target ?? 'Unknown'}.`,
    hidden: true,
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
  // Uses strict '>' to avoid marking any round as key when all rounds have 0 secret events.
  const keyRound = rounds.reduce((best, r) => {
    const secretCount = (r.events ?? []).filter(e => !e.visible).length
    if (secretCount === 0) return best
    const bestCount = (best?.events ?? []).filter(e => !e.visible).length
    return secretCount > bestCount ? r : best
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

// ── Narrator Highlight Reel (§12.3.15) ─────────────────────────────────────────

function HighlightReel({ segments }) {
  const [playingIdx, setPlayingIdx] = useState(null)
  const audioRef = useRef(null)

  // Stop audio on unmount (e.g. when "Play Again" is clicked mid-playback)
  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
    }
  }, [])

  if (!segments?.length) return null

  const handlePlay = (idx) => {
    // Stop current playback if any
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    if (playingIdx === idx) {
      setPlayingIdx(null)
      return
    }
    const seg = segments[idx]
    const audio = new Audio(`data:audio/wav;base64,${seg.audio_b64}`)
    audioRef.current = audio
    setPlayingIdx(idx)
    audio.play().catch(() => {})
    audio.onended = () => {
      setPlayingIdx(null)
      audioRef.current = null
    }
  }

  return (
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
        Narrator's Highlight Reel
      </h3>
      <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', marginBottom: 16 }}>
        The five most dramatic moments, as told by the narrator.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {segments.map((seg, idx) => {
          const isPlaying = playingIdx === idx
          return (
            <div
              key={idx}
              className="card fade-in"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                border: `1px solid ${isPlaying ? 'var(--accent)' : 'var(--border)'}`,
                background: isPlaying ? 'var(--accent-glow)' : 'var(--bg-card)',
                transition: 'all var(--transition)',
              }}
            >
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.875rem', color: 'var(--text)' }}>
                  {seg.description}
                </div>
                {seg.round > 0 && (
                  <div style={{ fontSize: '0.6875rem', color: 'var(--text-dim)', marginTop: 2 }}>
                    Round {seg.round}
                  </div>
                )}
              </div>
              <button
                onClick={() => handlePlay(idx)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 36,
                  height: 36,
                  borderRadius: '50%',
                  border: `1px solid ${isPlaying ? 'var(--accent)' : 'var(--border)'}`,
                  background: isPlaying ? 'var(--accent)' : 'var(--bg-elevated)',
                  color: isPlaying ? '#fff' : 'var(--text-muted)',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  flexShrink: 0,
                }}
              >
                {isPlaying ? '⏹' : '▶'}
              </button>
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
  const { winner, reveals, strategyLog, highlightReel, characterName: myCharacterName } = state

  // Guard against direct URL navigation or page refresh (no game state in context)
  if (!winner) return <Navigate to="/" replace />

  const handlePlayAgain = () => {
    dispatch({ type: 'RESET' })
    navigate('/')
  }

  const villagersWon = winner === 'villagers'
  const tannerWon = winner === 'tanner'
  // §12.3.10 Random Alignment: detect loyal AI from reveals
  const loyalAI = reveals.find(r => r.isAI && !r.isTraitor)
  const loyalAIVotedOut = winner === 'shapeshifter' && !!loyalAI

  const heroEmoji = villagersWon ? '🌅' : tannerWon ? '🪓' : loyalAIVotedOut ? '🤝' : '🐺'
  const heroTitle = villagersWon
    ? 'The Village Triumphs'
    : tannerWon
    ? 'The Tanner\'s Gambit'
    : loyalAIVotedOut
    ? 'You Betrayed Your Ally'
    : 'The Shapeshifter Wins'
  const heroSubtitle = villagersWon
    ? 'The darkness is lifted from Thornwood.'
    : tannerWon
    ? 'The Tanner played the village like a fiddle — voted out on purpose.'
    : loyalAIVotedOut
    ? `The village voted out ${loyalAI.characterName} — who was on your side the whole time.`
    : 'Thornwood falls to shadow and deception.'
  const heroColor = villagersWon ? 'var(--success)' : tannerWon ? 'var(--text-muted)' : 'var(--danger)'
  const heroGradient = villagersWon
    ? 'linear-gradient(180deg, rgba(22,163,74,0.15) 0%, transparent 100%)'
    : tannerWon
    ? 'linear-gradient(180deg, rgba(120,120,120,0.1) 0%, transparent 100%)'
    : 'linear-gradient(180deg, rgba(220,38,38,0.15) 0%, transparent 100%)'

  return (
    <div className="page">
      {/* Hero */}
      <div
        style={{
          background: heroGradient,
          paddingTop: 48,
          paddingBottom: 32,
          textAlign: 'center',
        }}
      >
        <div style={{ fontSize: '3.5rem', marginBottom: 12 }}>
          {heroEmoji}
        </div>
        <h1
          style={{
            fontFamily: 'var(--font-heading)',
            fontSize: '1.75rem',
            color: heroColor,
            marginBottom: 8,
          }}
        >
          {heroTitle}
        </h1>
        <p style={{ fontSize: '0.9375rem', fontStyle: 'italic', color: 'var(--text-muted)' }}>
          {heroSubtitle}
        </p>
      </div>

      {/* AI Teaser — pull-quote from the timeline to drive scroll-through */}
      {(() => {
        const allEvents = strategyLog.flatMap(r => r.events ?? [])
        const firstSecret = allEvents.find(e => !e.visible && EVENT_RENDERERS[e.type])
        const fallbackHighlight = highlightReel?.[0]
        const teaserText = firstSecret
          ? EVENT_RENDERERS[firstSecret.type](firstSecret).text
          : fallbackHighlight?.description ?? null
        if (!teaserText) return null
        return (
          <div
            style={{
              borderLeft: '3px solid var(--danger)',
              margin: '0 auto',
              maxWidth: 480,
              padding: '12px 20px',
              background: 'rgba(220,38,38,0.06)',
            }}
          >
            <div style={{ fontSize: '0.625rem', color: 'var(--danger)', textTransform: 'uppercase', letterSpacing: '0.12em', marginBottom: 6 }}>
              🔴 What the village didn't see
            </div>
            <p style={{ fontStyle: 'italic', fontSize: '0.875rem', color: 'var(--text-muted)', margin: 0, lineHeight: 1.5 }}>
              "{teaserText}"
            </p>
            <a
              href="#timeline"
              onClick={e => {
                e.preventDefault()
                document.getElementById('timeline')?.scrollIntoView({ behavior: 'smooth' })
              }}
              style={{ display: 'inline-block', marginTop: 10, fontSize: '0.75rem', color: 'var(--accent)', textDecoration: 'none' }}
            >
              ↓ See what the AI was really thinking
            </a>
          </div>
        )
      })()}

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
                const isTraitor = r.isTraitor ?? (r.role === 'shapeshifter')
                const isLoyalAIChar = r.isAI && !r.isTraitor
                const cardBorder = isTraitor ? 'var(--danger)'
                  : isLoyalAIChar ? 'var(--success)'
                  : isMe ? 'var(--border-accent)'
                  : 'var(--border)'
                return (
                  <div
                    key={r.characterName}
                    className="card fade-in"
                    style={{
                      border: `1px solid ${cardBorder}`,
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
                              color: isTraitor ? 'var(--danger)' : isLoyalAIChar ? 'var(--success)' : 'var(--text)',
                            }}
                          >
                            {r.characterName}
                          </div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            {r.playerName}
                            {isLoyalAIChar && ' — was on your side'}
                          </div>
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <span
                          className={`badge ${isTraitor ? 'badge-danger' : isLoyalAIChar ? 'badge-success' : 'badge-muted'}`}
                          style={{ fontSize: '0.625rem' }}
                        >
                          {isLoyalAIChar ? 'Loyal AI' : r.role ? r.role.charAt(0).toUpperCase() + r.role.slice(1) : '?'}
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

        {/* Narrator Highlight Reel (§12.3.15) */}
        <HighlightReel segments={highlightReel} />

        {/* Post-game interactive timeline (§12.3.13) */}
        {strategyLog.length > 0 && (
          <div id="timeline" style={{ marginBottom: 32 }}>
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

        {/* Play Again + Share */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-primary btn-lg" onClick={handlePlayAgain}>
            🔥 Play Again
          </button>
          <ShareButton winner={winner} reveals={reveals} />
        </div>
      </div>
    </div>
  )
}
