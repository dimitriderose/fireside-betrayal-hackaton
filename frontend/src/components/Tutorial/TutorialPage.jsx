import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

// ── Scripted mock data ────────────────────────────────────────────────────────

const MOCK_CAST = [
  { name: 'Blacksmith Garin', icon: '⚒️' },
  { name: 'Elder Sylva', icon: '🌿' },
  { name: 'Miller Brant', icon: '🌾' },
]

const MOCK_TIMELINE = [
  {
    round: 1,
    events: [
      { id: 'e1', type: 'night_investigation', actor: 'Herbalist Mira', target: 'Blacksmith Garin', data: { result: false, is_drunk: false }, visible: false },
      { id: 'e2', type: 'night_kill_attempt', actor: 'Elder Sylva', target: 'Miller Brant', data: { blocked: false }, visible: false },
      { id: 'e3', type: 'elimination', actor: null, target: 'Miller Brant', data: { was_traitor: false, role: 'villager', by_vote: true }, visible: true },
    ],
  },
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

// ── Step panels ────────────────────────────────────────────────────────────────

function StepRoleCard({ onComplete }) {
  const [revealed, setRevealed] = useState(false)

  const handleTap = () => {
    if (!revealed) {
      setRevealed(true)
      setTimeout(onComplete, 1200)
    }
  }

  return (
    <div style={{ padding: '0 16px' }}>
      <div
        onClick={handleTap}
        className={revealed ? 'card' : 'card pulse-glow'}
        style={{
          cursor: revealed ? 'default' : 'pointer',
          padding: '20px 16px',
          textAlign: 'center',
          border: `2px solid ${revealed ? 'var(--border-accent)' : 'var(--accent)'}`,
          transition: 'all 0.4s ease',
        }}
      >
        <div style={{ fontSize: '2.5rem', marginBottom: 8 }}>🔮</div>
        <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--accent)', fontFamily: 'var(--font-heading)' }}>
          Seer
        </div>
        <div style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: 6 }}>
          Herbalist Mira
        </div>
        {revealed && (
          <div className="fade-in" style={{ marginTop: 12, fontSize: '0.8125rem', color: 'var(--text)', lineHeight: 1.5 }}>
            Each night you may investigate one character to learn if they are the Shapeshifter.
          </div>
        )}
        {!revealed && (
          <div style={{ marginTop: 12, fontSize: '0.75rem', color: 'var(--text-dim)' }}>
            Tap to reveal
          </div>
        )}
      </div>
    </div>
  )
}

function StepNight({ onComplete }) {
  const [selected, setSelected] = useState(null)
  const [result, setResult] = useState(null)

  const handleSelect = (name) => {
    if (selected) return
    setSelected(name)
    setTimeout(() => {
      setResult({ target: name, isShapeshifter: false })
      setTimeout(onComplete, 1500)
    }, 600)
  }

  return (
    <div style={{ padding: '0 16px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 12 }}>
        {MOCK_CAST.map(c => (
          <div
            key={c.name}
            onClick={() => handleSelect(c.name)}
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
            <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.2 }}>
              {c.name.split(' ').join('\n')}
            </div>
          </div>
        ))}
      </div>
      {result && (
        <div className="card fade-in" style={{ textAlign: 'center', padding: '10px 14px', border: '1px solid #60a5fa' }}>
          <span style={{ color: '#60a5fa', fontSize: '0.875rem' }}>
            🔮 {result.target} is <strong>NOT</strong> the Shapeshifter.
          </span>
        </div>
      )}
    </div>
  )
}

function StepDiscussion({ onComplete }) {
  const [reacted, setReacted] = useState(false)
  const [messages, setMessages] = useState([
    { speaker: 'Elder Sylva', text: 'Something feels wrong in Thornwood tonight...', source: 'ai_character' },
    { speaker: 'Blacksmith Garin', text: 'I was at the forge. Ask the miller if you doubt me.', source: 'ai_character' },
  ])

  const handleReaction = (type, target) => {
    if (reacted) return
    setReacted(true)
    const text = type === 'suspect'
      ? `Herbalist Mira eyes ${target} with suspicion.`
      : `Herbalist Mira nods in agreement with ${target}.`
    setMessages(prev => [...prev, { speaker: 'Herbalist Mira', text, source: 'player' }])
    setTimeout(onComplete, 1500)
  }

  return (
    <div style={{ padding: '0 16px' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10, maxHeight: 140, overflowY: 'auto' }}>
        {messages.map((m, i) => (
          <div key={i} style={{ display: 'flex', gap: 8 }}>
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

  const handleVote = (name) => {
    if (voted) return
    setVoted(name)
    setTimeout(onComplete, 1500)
  }

  return (
    <div style={{ padding: '0 16px' }}>
      <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: 10 }}>
        Who is the Shapeshifter?
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {MOCK_CAST.map(c => (
          <button
            key={c.name}
            onClick={() => handleVote(c.name)}
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
    </div>
  )
}

function StepGameOver({ onDone }) {
  return (
    <div style={{ padding: '0 16px' }}>
      <div style={{ marginBottom: 12 }}>
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
            <span style={{ fontSize: '0.8125rem' }}>Miller Brant was eliminated by vote.</span>
          </div>
        </div>
      </div>
      <button className="btn btn-primary btn-lg" onClick={onDone} style={{ width: '100%' }}>
        🔥 Start a Real Game
      </button>
    </div>
  )
}

// ── Tutorial script steps ─────────────────────────────────────────────────────

const STEPS = [
  {
    narrator: "Welcome to Fireside: Betrayal. Tonight, you play as Herbalist Mira — the Seer. Each night a hidden Shapeshifter eliminates a villager. The village must vote them out. Tap your role card to learn your ability.",
    prompt: 'Tap the glowing role card to reveal your power.',
    panel: (onComplete) => <StepRoleCard onComplete={onComplete} />,
  },
  {
    narrator: "Night falls over Thornwood. As the Seer, you may peer into one villager's soul. Tap a character to investigate them.",
    prompt: 'Tap any character card to investigate.',
    panel: (onComplete) => <StepNight onComplete={onComplete} />,
  },
  {
    narrator: "Dawn breaks. The village gathers. Use a quick reaction to join the discussion — tap to voice your suspicion.",
    prompt: 'Tap a quick reaction to speak.',
    panel: (onComplete) => <StepDiscussion onComplete={onComplete} />,
  },
  {
    narrator: "Time to vote. Who do you think is the Shapeshifter lurking in Thornwood? Tap a character to cast your ballot.",
    prompt: 'Tap a character to vote.',
    panel: (onComplete) => <StepVote onComplete={onComplete} />,
  },
  {
    narrator: "The village has spoken. Now the hidden truth is revealed — every secret action from tonight, laid bare.",
    prompt: 'Explore the timeline, then start your real game.',
    panel: (_, onDone) => <StepGameOver onDone={onDone} />,
  },
]

// ── Main TutorialPage ─────────────────────────────────────────────────────────

export default function TutorialPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(0)

  const handleComplete = () => {
    if (step < STEPS.length - 1) setStep(s => s + 1)
  }

  const handleSkip = () => navigate('/')
  const handleDone = () => navigate('/')

  const current = STEPS[step]

  return (
    <div className="page" style={{ maxWidth: 480, margin: '0 auto' }}>
      <TutorialProgress step={step + 1} total={STEPS.length} onSkip={handleSkip} />

      <div style={{ paddingTop: 24, paddingBottom: 8 }}>
        <NarratorBubble text={current.narrator} highlighted={true} />
        <HighlightPrompt text={current.prompt} />
      </div>

      <div className="fade-in" key={step}>
        {step < STEPS.length - 1
          ? current.panel(handleComplete)
          : current.panel(handleComplete, handleDone)
        }
      </div>
    </div>
  )
}
