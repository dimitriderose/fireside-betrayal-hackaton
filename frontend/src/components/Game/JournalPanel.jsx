/**
 * JournalPanel — Seer investigation history.
 * Displays a scrollable list of investigation results from the Seer role.
 */
export default function JournalPanel({ investigations }) {
  if (!investigations || investigations.length === 0) {
    return (
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '32px 16px',
          minHeight: 120,
          maxHeight: '45vh',
        }}
      >
        <div style={{ fontSize: '2rem', marginBottom: 12 }}>&#128302;</div>
        <p style={{ color: 'var(--text-dim)', fontSize: '0.875rem', textAlign: 'center' }}>
          No investigations yet
        </p>
      </div>
    )
  }

  return (
    <div
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '12px 16px',
        maxWidth: 420,
        width: '100%',
        margin: '0 auto',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
        minHeight: 120,
        maxHeight: '45vh',
      }}
    >
      {investigations.map((inv, i) => (
        <div
          key={i}
          style={{
            background: 'var(--bg-card)',
            border: `1px solid ${inv.isShapeshifter ? 'var(--danger)' : 'var(--border)'}`,
            borderRadius: 'var(--radius-md)',
            padding: '10px 12px',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 4,
            }}
          >
            <span
              style={{
                fontSize: '0.6875rem',
                color: 'var(--text-muted)',
                textTransform: 'uppercase',
                letterSpacing: '0.06em',
              }}
            >
              Round {inv.round}
            </span>
            <span style={{ fontSize: '1.1rem' }}>
              {inv.isShapeshifter ? '\u{1F480}' : '\u{2705}'}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                fontFamily: 'var(--font-heading)',
                fontSize: '0.95rem',
                color: inv.isShapeshifter ? 'var(--danger)' : 'var(--text)',
                fontWeight: 600,
              }}
            >
              {inv.target}
            </span>
          </div>
          <div
            style={{
              fontSize: '0.8125rem',
              color: inv.isShapeshifter ? 'var(--danger)' : '#60a5fa',
              marginTop: 4,
              fontStyle: 'italic',
            }}
          >
            {inv.isShapeshifter ? 'Shapeshifter detected!' : 'Appears to be innocent'}
          </div>
        </div>
      ))}
    </div>
  )
}
