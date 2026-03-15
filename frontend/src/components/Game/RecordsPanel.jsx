import { useMemo } from 'react'

/**
 * RecordsPanel — Vote history across all rounds.
 * Shows per-round vote breakdown with bars, voter names, and eliminated badges.
 */
export default function RecordsPanel({ voteHistory }) {
  if (!voteHistory || voteHistory.length === 0) {
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
        <p style={{ color: 'var(--text-dim)', fontSize: '0.875rem', textAlign: 'center' }}>
          No votes recorded yet
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
        gap: 16,
        minHeight: 120,
        maxHeight: '45vh',
      }}
    >
      {voteHistory.map((record, ri) => (
        <RoundRecord key={ri} record={record} />
      ))}
    </div>
  )
}

function RoundRecord({ record }) {
  const { round, tally, individualVotes, eliminated, wasTraitor, role, isTie } = record

  const candidates = useMemo(() => {
    return Object.entries(tally)
      .sort(([, a], [, b]) => b - a)
      .map(([name, count]) => {
        const voters = Object.entries(individualVotes ?? {})
          .filter(([, target]) => target === name)
          .map(([voter]) => voter)
        return { name, count, voters, isEliminated: name === eliminated }
      })
  }, [tally, individualVotes, eliminated])

  const totalVotes = Object.values(tally).reduce((sum, c) => sum + c, 0)

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
      }}
    >
      {/* Round header */}
      <div
        style={{
          padding: '8px 12px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-heading)',
            fontSize: '0.875rem',
            color: 'var(--accent)',
            fontWeight: 600,
          }}
        >
          Round {round}
        </span>
        {isTie && (
          <span style={{ fontSize: '0.6875rem', color: 'var(--text-dim)', fontStyle: 'italic' }}>
            Tied vote
          </span>
        )}
      </div>

      {/* Candidate rows */}
      <div style={{ padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {candidates.map(({ name, count, voters, isEliminated: isElim }) => (
          <div
            key={name}
            style={{
              padding: '8px 10px',
              borderRadius: 'var(--radius)',
              border: `1px solid ${isElim ? 'var(--danger)' : 'var(--border)'}`,
              background: isElim ? 'rgba(220, 38, 38, 0.08)' : 'var(--bg-elevated)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span
                style={{
                  fontFamily: 'var(--font-heading)',
                  fontSize: '0.85rem',
                  color: isElim ? 'var(--danger)' : 'var(--text)',
                }}
              >
                {isElim ? '\u{1F480} ' : ''}{name}
                {isElim && role && (
                  <span
                    style={{
                      fontSize: '0.6875rem',
                      color: wasTraitor ? 'var(--accent)' : 'var(--text-muted)',
                      marginLeft: 6,
                      fontWeight: 500,
                    }}
                  >
                    ({role})
                  </span>
                )}
              </span>
              <span style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                {count} {count === 1 ? 'vote' : 'votes'}
              </span>
            </div>

            {/* Vote bar */}
            <div
              style={{
                height: 4,
                borderRadius: 2,
                background: 'var(--border)',
                marginBottom: 4,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${totalVotes > 0 ? (count / totalVotes) * 100 : 0}%`,
                  background: isElim ? 'var(--danger)' : 'var(--accent)',
                  borderRadius: 2,
                  transition: 'width 0.6s ease',
                }}
              />
            </div>

            {/* Voter names */}
            {voters.length > 0 && (
              <div style={{ fontSize: '0.6875rem', color: 'var(--text-dim)' }}>
                {voters.join(', ')}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Outcome */}
      {eliminated && (
        <div
          style={{
            textAlign: 'center',
            fontSize: '0.75rem',
            color: 'var(--text-muted)',
            fontStyle: 'italic',
            borderTop: '1px solid var(--border)',
            padding: '8px 12px',
          }}
        >
          <strong style={{ color: wasTraitor ? 'var(--accent)' : 'var(--danger)' }}>
            {eliminated}
          </strong>
          {' was cast out. '}
          {wasTraitor
            ? <strong style={{ color: 'var(--accent)' }}>They were the Shapeshifter!</strong>
            : <span>They were a <strong>{role ?? 'unknown role'}</strong>.</span>
          }
        </div>
      )}
    </div>
  )
}
