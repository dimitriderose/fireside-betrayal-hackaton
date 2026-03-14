import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { RosterIconStrip } from '../Game/RosterPanel.jsx'
import VoteTallyOverlay from '../Voting/VoteTallyOverlay.jsx'

// ── Scripted mock data ────────────────────────────────────────────────────────

const MOCK_CAST = [
  { name: 'Blacksmith Garin', icon: '⚒️' },
  { name: 'Elder Sylva', icon: '🌿' },
  { name: 'Miller Brant', icon: '🌾' },
]

const MOCK_ROSTER_PLAYERS = [
  { characterName: 'Herbalist Mira', alive: true },
  { characterName: 'Blacksmith Garin', alive: true },
  { characterName: 'Elder Sylva', alive: true },
  { characterName: 'Miller Brant', alive: true },
]

const MOCK_AI_CHARACTERS = [
  { name: 'Weaver Isolde', alive: true },
]

const MOCK_VOTE_RESULT = {
  tally: { 'Elder Sylva': 3, 'Blacksmith Garin': 1 },
  individualVotes: {
    'Herbalist Mira': 'Elder Sylva',
    'Miller Brant': 'Elder Sylva',
    'Weaver Isolde': 'Elder Sylva',
    'Blacksmith Garin': 'Miller Brant',
  },
  eliminated: 'Elder Sylva',
  wasTraitor: true,
  role: 'shapeshifter',
  isTie: false,
}

const ROLE_INFO = {
  seer: { icon: '🔮', label: 'Seer' },
}

const ROLE_DESC = {
  seer: 'Each night you may investigate one character to learn if they are the Shapeshifter.',
}

const PRESETS = [
  { id: 'classic',  label: '⚔️ Classic',  desc: 'Deep, dramatic fantasy narrator',
    sample: '"The accused stands before you. Speak your defence, if you dare."' },
  { id: 'campfire', label: '🔥 Campfire', desc: 'Warm storyteller among friends',
    sample: '"Pull up a log, friend. The night\'s young and the fire\'s warm."' },
  { id: 'horror',   label: '🕯️ Horror',   desc: 'Slow, unsettling dread',
    sample: '"Something watches from beyond the treeline. It always has."' },
  { id: 'comedy',   label: '😏 Comedy',   desc: 'Wry, self-aware humor',
    sample: '"Congratulations — you\'ve all survived round one. Mostly."' },
]

// ── Sub-components ────────────────────────────────────────────────────────────

function TutorialProgress({ step, total, onSkip }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '10px 16px',
      borderBottom: '1px solid var(--border)',
      background: 'var(--bg-elevated)',
    }}>
      <div style={{ display: 'flex', gap: 6 }}>
        {Array.from({ length: total }).map((_, i) => (
          <div
            key={i}
            style={{
              width: i < step ? 20 : 8,
              height: 6,
              borderRadius: 'var(--radius-full)',
              background: i < step ? 'var(--accent)' : 'var(--border)',
              transition: 'all 0.3s ease',
            }}
          />
        ))}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
          Step {step} of {total}
        </span>
        <button
          className="btn btn-ghost btn-sm"
          onClick={onSkip}
          style={{ fontSize: '0.75rem' }}
        >
          Skip Tutorial
        </button>
      </div>
    </div>
  )
}

function NarratorBubble({ text, highlighted }) {
  return (
    <div
      style={{
        background: highlighted ? 'rgba(255,107,53,0.08)' : 'var(--bg-card)',
        border: `1px solid ${highlighted ? 'var(--border-accent)' : 'var(--border)'}`,
        borderRadius: 'var(--radius-md)',
        padding: '12px 16px',
        margin: '0 16px 12px',
        fontSize: '0.875rem',
        fontStyle: 'italic',
        color: 'var(--accent)',
        lineHeight: 1.6,
        animation: highlighted ? 'pulse-glow 2s ease-in-out infinite' : 'none',
      }}
      className="fade-in"
    >
      🔥 {text}
    </div>
  )
}

function HighlightPrompt({ text }) {
  return (
    <div style={{
      textAlign: 'center',
      padding: '8px 16px',
      marginBottom: 8,
      fontSize: '0.8125rem',
      color: 'var(--text-muted)',
    }}>
      ↓ {text}
    </div>
  )
}

// ── Role Reveal Overlay (copied from GameScreen) ─────────────────────────────

function RoleRevealOverlay({ role, characterName, onDismiss }) {
  const info = ROLE_INFO[role] ?? {}
  const desc = ROLE_DESC[role] ?? 'Your secret role in Thornwood.'

  useEffect(() => {
    const timer = setTimeout(onDismiss, 10000)
    return () => clearTimeout(timer)
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

// ── Step panels ────────────────────────────────────────────────────────────────

function StepRoleCard({ onComplete }) {
  const [showOverlay, setShowOverlay] = useState(true)
  const dismissed = useRef(false)

  const handleDismiss = useCallback(() => {
    if (dismissed.current) return
    dismissed.current = true
    setShowOverlay(false)
    setTimeout(onComplete, 800)
  }, [onComplete])

  return (
    <div style={{ padding: '0 16px' }}>
      {showOverlay && (
        <RoleRevealOverlay
          role="seer"
          characterName="Herbalist Mira"
          onDismiss={handleDismiss}
        />
      )}
      {!showOverlay && (
        <div className="card fade-in" style={{
          padding: '20px 16px',
          textAlign: 'center',
          border: '2px solid var(--border-accent)',
        }}>
          <div style={{ fontSize: '2.5rem', marginBottom: 8 }}>🔮</div>
          <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--accent)', fontFamily: 'var(--font-heading)' }}>
            Seer
          </div>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: 6 }}>
            Herbalist Mira
          </div>
          <div style={{ marginTop: 12, fontSize: '0.8125rem', color: 'var(--text)', lineHeight: 1.5 }}>
            Each night you may investigate one character to learn if they are the Shapeshifter.
          </div>
        </div>
      )}
    </div>
  )
}

function StepNight({ onComplete }) {
  const [selected, setSelected] = useState(null)
  const [result, setResult] = useState(null)
  const [pttDone, setPttDone] = useState(false)
  const [pttHolding, setPttHolding] = useState(false)
  const [pttResponse, setPttResponse] = useState(false)

  const handleSelect = (name) => {
    if (selected) return
    setSelected(name)
    setTimeout(() => {
      setResult({ target: name, isShapeshifter: false })
    }, 600)
  }

  const handlePttDown = () => {
    if (pttDone) return
    setPttHolding(true)
  }

  const handlePttUp = () => {
    if (!pttHolding || pttDone) return
    setPttHolding(false)
    setPttDone(true)
    setPttResponse(true)
    setTimeout(onComplete, 2000)
  }

  return (
    <div style={{ padding: '0 16px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 12 }}>
        {MOCK_CAST.map(c => (
          <div
            key={c.name}
            role="button"
            tabIndex={selected ? -1 : 0}
            onClick={() => handleSelect(c.name)}
            onKeyDown={(e) => e.key === 'Enter' && handleSelect(c.name)}
            aria-label={`Investigate ${c.name}`}
            className={selected === c.name ? 'card' : 'card pulse-glow'}
            style={{
              cursor: selected ? 'default' : 'pointer',
              textAlign: 'center',
              padding: '12px 8px',
              border: `1px solid ${selected === c.name ? 'var(--border-accent)' : 'var(--border)'}`,
              opacity: selected && selected !== c.name ? 0.5 : 1,
              transition: 'all 0.3s',
            }}
          >
            <div style={{ fontSize: '1.5rem' }}>{c.icon}</div>
            <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.2, whiteSpace: 'pre-line' }}>
              {c.name.split(' ').join('\n')}
            </div>
          </div>
        ))}
      </div>
      {result && (
        <div className="card fade-in" style={{ textAlign: 'center', padding: '10px 14px', border: '1px solid #60a5fa', marginBottom: 12 }}>
          <span style={{ color: '#60a5fa', fontSize: '0.875rem' }}>
            🔮 {result.target} is <strong>NOT</strong> the Shapeshifter.
          </span>
        </div>
      )}

      {/* Mock Push-to-Talk */}
      {result && !pttResponse && (
        <div className="fade-in" style={{ textAlign: 'center', marginTop: 8 }}>
          <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: 8 }}>
            This is a voice-first game. Hold the button to speak to the Narrator.
          </div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
            <button
              className={`btn ${pttHolding ? 'btn-danger' : 'btn-primary'}`}
              onPointerDown={handlePttDown}
              onPointerUp={handlePttUp}
              onPointerLeave={(e) => { e.preventDefault(); if (pttHolding) handlePttUp() }}
              aria-label={pttHolding ? 'Release to send your message' : 'Hold to speak to the Narrator'}
              style={{
                padding: '8px 20px',
                fontSize: '0.875rem',
                touchAction: 'none',
                animation: pttHolding ? 'none' : 'pulse-glow 2s ease-in-out infinite',
              }}
            >
              {pttHolding ? 'Release to Send' : 'Hold to Speak'}
            </button>
            {pttHolding && (
              <span className="fade-in" style={{ fontSize: '0.75rem', color: 'var(--success)' }}>
                <span className="pulse-glow" style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'var(--success)', marginRight: 4 }} />
                The Narrator is listening...
              </span>
            )}
          </div>
        </div>
      )}

      {pttResponse && (
        <div className="fade-in" style={{ marginTop: 8 }}>
          <NarratorBubble
            text="The Narrator listens. Speak when the fire glows — your voice carries to Thornwood."
            highlighted={true}
          />
        </div>
      )}
    </div>
  )
}

function StepDiscussion({ onComplete }) {
  const [reacted, setReacted] = useState(false)
  const reactedRef = useRef(false)
  const [messages, setMessages] = useState([
    { id: 'm1', speaker: 'Elder Sylva', text: 'Something feels wrong in Thornwood tonight...', source: 'ai_character' },
    { id: 'm2', speaker: 'Blacksmith Garin', text: 'I was at the forge. Ask the miller if you doubt me.', source: 'ai_character' },
  ])

  const handleReaction = (type, target) => {
    if (reactedRef.current) return
    reactedRef.current = true
    setReacted(true)
    const text = type === 'suspect'
      ? `Herbalist Mira eyes ${target} with suspicion.`
      : `Herbalist Mira nods in agreement with ${target}.`
    setMessages(prev => [...prev, { id: `m${Date.now()}`, speaker: 'Herbalist Mira', text, source: 'player' }])
    setTimeout(onComplete, 1500)
  }

  return (
    <div style={{ padding: '0 16px' }}>
      {/* Roster strip */}
      <RosterIconStrip
        players={MOCK_ROSTER_PLAYERS}
        myCharacterName="Herbalist Mira"
        aiCharacters={MOCK_AI_CHARACTERS}
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10, marginTop: 10, maxHeight: 140, overflowY: 'auto' }}>
        {messages.map((m) => (
          <div key={m.id} style={{ display: 'flex', gap: 8 }}>
            <span style={{
              fontSize: '0.75rem',
              fontWeight: 600,
              color: m.source === 'player' ? 'var(--accent)' : 'var(--text)',
              minWidth: 100,
            }}>
              {m.speaker}:
            </span>
            <span style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>{m.text}</span>
          </div>
        ))}
      </div>
      {!reacted && (
        <div
          className="pulse-glow"
          style={{ display: 'flex', gap: 6, flexWrap: 'wrap', padding: '8px', borderRadius: 'var(--radius-md)', border: '1px solid var(--accent)' }}
        >
          {MOCK_CAST.map(c => (
            <button
              key={c.name}
              className="btn btn-ghost btn-sm"
              onClick={() => handleReaction('suspect', c.name)}
              style={{ fontSize: '0.75rem' }}
            >
              🔍 Suspect {c.name.split(' ')[1]}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function StepVote({ onComplete }) {
  const [voted, setVoted] = useState(null)
  const [showTally, setShowTally] = useState(false)

  const handleVote = (name) => {
    if (voted) return
    setVoted(name)
    setTimeout(() => setShowTally(true), 800)
    setTimeout(onComplete, 5000)
  }

  return (
    <div style={{ padding: '0 16px' }}>
      <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: 10 }}>
        Who is the Shapeshifter?
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
        {MOCK_CAST.map(c => (
          <button
            key={c.name}
            onClick={() => handleVote(c.name)}
            aria-pressed={voted === c.name}
            className={voted === c.name ? 'btn btn-primary' : 'btn btn-ghost pulse-glow'}
            style={{ justifyContent: 'flex-start', gap: 10, padding: '10px 14px' }}
            disabled={!!voted && voted !== c.name}
          >
            <span style={{ fontSize: '1.25rem' }}>{c.icon}</span>
            {c.name}
            {voted === c.name && ' — voted!'}
          </button>
        ))}
      </div>
      {showTally && <VoteTallyOverlay voteResult={MOCK_VOTE_RESULT} />}
    </div>
  )
}

function StepGameOver({ onDone }) {
  const [selectedPreset, setSelectedPreset] = useState(null)

  return (
    <div style={{ padding: '0 16px' }}>
      {/* Timeline reveal */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>
          What Really Happened — Round 1
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div className="card fade-in" style={{ display: 'flex', gap: 8, padding: '8px 10px', border: '1px solid rgba(220,38,38,0.3)' }}>
            <span>🔮</span>
            <span style={{ fontSize: '0.8125rem' }}>Herbalist Mira investigated Blacksmith Garin: <strong>NOT</strong> the Shapeshifter.</span>
          </div>
          <div className="card fade-in" style={{ display: 'flex', gap: 8, padding: '8px 10px', border: '1px solid rgba(220,38,38,0.3)' }}>
            <span>🗡️</span>
            <span style={{ fontSize: '0.8125rem' }}>Elder Sylva targeted Miller Brant.</span>
          </div>
          <div className="card fade-in" style={{ display: 'flex', gap: 8, padding: '8px 10px', border: '1px solid var(--border)' }}>
            <span>⚰️</span>
            <span style={{ fontSize: '0.8125rem' }}>Elder Sylva was eliminated by vote — <strong style={{ color: 'var(--accent)' }}>the Shapeshifter!</strong></span>
          </div>
        </div>
      </div>

      {/* Narrator presets */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>
          Choose Your Narrator
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          {PRESETS.map(p => (
            <div
              key={p.id}
              onClick={() => setSelectedPreset(p.id)}
              className="card"
              style={{
                cursor: 'pointer',
                padding: '10px 12px',
                textAlign: 'center',
                border: `1px solid ${selectedPreset === p.id ? 'var(--accent)' : 'var(--border)'}`,
                background: selectedPreset === p.id ? 'rgba(255,107,53,0.08)' : 'var(--bg-card)',
                transition: 'all 0.2s',
              }}
            >
              <div style={{ fontSize: '0.875rem', fontWeight: 600 }}>{p.label}</div>
              <div style={{ fontSize: '0.6875rem', color: 'var(--text-dim)', marginTop: 2 }}>{p.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Show selected preset sample in narrator bubble */}
      {selectedPreset && (
        <NarratorBubble
          text={PRESETS.find(p => p.id === selectedPreset)?.sample ?? ''}
          highlighted={true}
        />
      )}

      <button className="btn btn-primary btn-lg" onClick={onDone} style={{ width: '100%' }}>
        🔥 Start a Real Game
      </button>
    </div>
  )
}

// ── Tutorial script steps ─────────────────────────────────────────────────────

const STEPS = [
  {
    narrator: "Welcome to Fireside: Betrayal. Tonight, you play as Herbalist Mira — the Seer. Each night a hidden Shapeshifter eliminates a villager. The village must vote them out. Your role is about to be revealed...",
    prompt: 'Tap anywhere to dismiss the reveal and continue.',
    panel: (onComplete) => <StepRoleCard onComplete={onComplete} />,
  },
  {
    narrator: "Night falls over Thornwood. As the Seer, you may peer into one villager's soul. Tap a character to investigate them.",
    prompt: 'Tap any character card to investigate.',
    panel: (onComplete) => <StepNight onComplete={onComplete} />,
  },
  {
    narrator: "Dawn breaks. The village gathers around the fire. Use a quick reaction to join the discussion — tap to voice your suspicion.",
    prompt: 'Tap a quick reaction to speak.',
    panel: (onComplete) => <StepDiscussion onComplete={onComplete} />,
  },
  {
    narrator: "Time to vote. Who do you think is the Shapeshifter lurking in Thornwood? Tap a character to cast your ballot.",
    prompt: 'Tap a character to vote.',
    panel: (onComplete) => <StepVote onComplete={onComplete} />,
  },
  {
    narrator: "Every secret laid bare. But the narrator's voice can change — tap a style to listen.",
    prompt: 'Explore the timeline, pick a narrator, then start your real game.',
    panel: (_, onDone) => <StepGameOver onDone={onDone} />,
  },
]

// ── Main TutorialPage ─────────────────────────────────────────────────────────

export default function TutorialPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)

  const handleComplete = useCallback(() => {
    setStep(s => s < STEPS.length - 1 ? s + 1 : s)
  }, [])

  const handleSkip = () => navigate('/')
  const handleDone = () => navigate('/join?host=true')

  const current = STEPS[step]

  return (
    <div className="page" style={{ maxWidth: 480, margin: '0 auto' }}>
      <TutorialProgress step={step + 1} total={STEPS.length} onSkip={handleSkip} />

      <div style={{ paddingTop: 24, paddingBottom: 8 }}>
        <NarratorBubble key={step} text={current.narrator} highlighted={true} />
        <HighlightPrompt text={current.prompt} />
      </div>

      <div className="fade-in" key={step}>
        {current.panel(handleComplete, handleDone)}
      </div>
    </div>
  )
}
