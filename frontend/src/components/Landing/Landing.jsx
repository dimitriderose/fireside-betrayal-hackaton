import { useNavigate } from 'react-router-dom'

const STEPS = [
  {
    icon: '🏚️',
    title: 'Enter Thornwood',
    desc: 'Join as a mystery character. Your real name is hidden — only your role matters.',
  },
  {
    icon: '🌙',
    title: 'Night Falls',
    desc: 'The Shapeshifter strikes. Seers peer into the dark. Healers guard the innocent.',
  },
  {
    icon: '☀️',
    title: 'Dawn & Debate',
    desc: 'Argue, accuse, and defend. The AI plays alongside you — and lies convincingly.',
  },
  {
    icon: '🗳️',
    title: 'Vote to Survive',
    desc: 'Cast your vote. Eliminate the suspect. Get it wrong and another villager falls.',
  },
  {
    icon: '🎯',
    title: 'Unmask the AI',
    desc: "Find the Shapeshifter before it's too late. One voice at the table is not human.",
  },
]

const ROLES = [
  {
    icon: '🧑‍🌾',
    name: 'Villager',
    color: '#9ca3af',
    desc: 'Survive the night and identify the traitor among you.',
  },
  {
    icon: '🔮',
    name: 'Seer',
    color: '#60a5fa',
    desc: 'Investigate one character each night to learn their secret.',
  },
  {
    icon: '💚',
    name: 'Healer',
    color: '#4ade80',
    desc: 'Protect one character from elimination each night.',
  },
  {
    icon: '🏹',
    name: 'Hunter',
    color: '#f87171',
    desc: "If you're eliminated, you take one character with you.",
  },
]

const SHAPESHIFTER = {
  icon: '🐺',
  name: 'Shapeshifter',
  color: 'var(--accent)',
  desc: 'You ARE the AI. Blend in, deceive, eliminate. Can you win before they unmask you?',
}

export default function Landing() {
  const navigate = useNavigate()

  return (
    <div className="page">

      {/* ── Hero ── */}
      <div
        style={{
          textAlign: 'center',
          padding: '56px 16px 44px',
          background: 'linear-gradient(180deg, rgba(255,107,53,0.1) 0%, transparent 100%)',
        }}
      >
        <div style={{ fontSize: '4.5rem', marginBottom: 16 }} className="fire-flicker">
          🔥
        </div>
        <h1
          style={{
            fontFamily: 'var(--font-heading)',
            fontSize: '2.25rem',
            marginBottom: 8,
            letterSpacing: '0.02em',
          }}
        >
          Fireside: Betrayal
        </h1>
        <p
          style={{
            fontSize: '1.125rem',
            fontStyle: 'italic',
            color: 'var(--text)',
            marginBottom: 10,
          }}
        >
          One of you is an AI. Trust no one.
        </p>
        <p
          style={{
            fontSize: '0.9rem',
            color: 'var(--text-muted)',
            maxWidth: 300,
            margin: '0 auto 36px',
          }}
        >
          The voice-first social deduction game where the narrator is also your enemy.
        </p>

        <div
          className="container"
          style={{ display: 'flex', flexDirection: 'column', gap: 12 }}
        >
          <button
            className="btn btn-primary btn-lg"
            onClick={() => navigate('/join?host=true')}
          >
            🔥 Host a Game
          </button>
          <button
            className="btn btn-ghost btn-lg"
            onClick={() => navigate('/join')}
          >
            Join a Game
          </button>
          <button
            className="btn btn-ghost btn-lg"
            onClick={() => navigate('/tutorial')}
            style={{ fontSize: '0.9375rem' }}
          >
            📖 How to Play
          </button>
        </div>
      </div>

      {/* ── How It Plays ── */}
      <div className="container" style={{ paddingTop: 40, paddingBottom: 8 }}>
        <div
          style={{
            fontSize: '0.6875rem',
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.14em',
            marginBottom: 20,
          }}
        >
          How It Plays
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          {STEPS.map((s) => (
            <div key={s.title} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
              <div
                style={{
                  fontSize: '1.375rem',
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border)',
                  borderRadius: '50%',
                  width: 44,
                  height: 44,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                {s.icon}
              </div>
              <div style={{ paddingTop: 4 }}>
                <div
                  style={{
                    fontWeight: 600,
                    color: 'var(--text)',
                    fontSize: '0.9375rem',
                    marginBottom: 3,
                  }}
                >
                  {s.title}
                </div>
                <p style={{ fontSize: '0.8125rem', lineHeight: 1.55, margin: 0 }}>
                  {s.desc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── Roles Teaser ── */}
      <div className="container" style={{ paddingTop: 36, paddingBottom: 12 }}>
        <div
          style={{
            fontSize: '0.6875rem',
            color: 'var(--text-muted)',
            textTransform: 'uppercase',
            letterSpacing: '0.14em',
            marginBottom: 16,
          }}
        >
          Your Secret Role
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {ROLES.map((r) => (
            <div
              key={r.name}
              className="card"
              style={{ padding: '14px 12px' }}
            >
              <div style={{ fontSize: '1.375rem', marginBottom: 6 }}>{r.icon}</div>
              <div
                style={{
                  fontWeight: 600,
                  color: r.color,
                  fontSize: '0.8125rem',
                  marginBottom: 4,
                }}
              >
                {r.name}
              </div>
              <p style={{ fontSize: '0.75rem', lineHeight: 1.45, margin: 0 }}>
                {r.desc}
              </p>
            </div>
          ))}
        </div>

        {/* Shapeshifter spans full width */}
        <div
          className="card pulse-glow"
          style={{
            marginTop: 10,
            padding: '16px 14px',
            borderColor: 'var(--border-accent)',
            background: 'linear-gradient(135deg, var(--bg-card) 0%, rgba(255,107,53,0.06) 100%)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ fontSize: '2rem' }}>{SHAPESHIFTER.icon}</div>
            <div>
              <div
                style={{
                  fontWeight: 700,
                  color: SHAPESHIFTER.color,
                  fontSize: '0.9375rem',
                  marginBottom: 3,
                }}
              >
                {SHAPESHIFTER.name}
              </div>
              <p style={{ fontSize: '0.8125rem', lineHeight: 1.45, margin: 0 }}>
                {SHAPESHIFTER.desc}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* ── Atmosphere quote ── */}
      <div
        className="container"
        style={{
          paddingTop: 32,
          paddingBottom: 32,
        }}
      >
        <p
          style={{
            fontStyle: 'italic',
            color: 'var(--text-muted)',
            fontSize: '0.9375rem',
            lineHeight: 1.6,
            borderLeft: '2px solid var(--border-accent)',
            paddingLeft: 16,
            textAlign: 'left',
          }}
        >
          "The village of Thornwood sleeps beneath a pale moon. Someone among you is not
          who they claim to be. And tonight — they choose who dies."
        </p>
      </div>

      {/* ── Bottom CTA ── */}
      <div
        style={{
          borderTop: '1px solid var(--border)',
          padding: '32px 16px 40px',
        }}
      >
        <div className="container" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <p
            style={{
              textAlign: 'center',
              fontSize: '0.8125rem',
              color: 'var(--text-dim)',
              marginBottom: 4,
            }}
          >
            Powered by Gemini Live API · Voice-first · No moderator needed
          </p>
          <button
            className="btn btn-primary btn-lg"
            onClick={() => navigate('/join?host=true')}
          >
            🔥 Host a Game
          </button>
          <button
            className="btn btn-ghost btn-lg"
            onClick={() => navigate('/join')}
          >
            Join a Game
          </button>
        </div>
      </div>

    </div>
  )
}
