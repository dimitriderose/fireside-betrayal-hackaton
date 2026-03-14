import { useMemo } from 'react'

/**
 * Displays vote results after the village votes.
 * Shows who voted for whom, the tally, and the outcome.
 */
export default function VoteTallyOverlay({ voteResult }) {
  if (!voteResult) return null

  const { tally, individualVotes, eliminated, wasTraitor, role, isTie } = voteResult

  // Sort candidates by vote count (descending)
  const candidates = useMemo(() => {
    return Object.entries(tally)
      .sort(([, a], [, b]) => b - a)
      .map(([name, count]) => {
        // Find who voted for this candidate
        const voters = Object.entries(individualVotes)
          .filter(([, target]) => target === name)
          .map(([voter]) => voter)
        return { name, count, voters, isEliminated: name === eliminated }
      })
  }, [tally, individualVotes, eliminated])

  const totalVotes = Object.values(tally).reduce((sum, c) => sum + c, 0)

  return (
    <div className="card fade-in" style={{
      borderColor: 'var(--border-accent)',
      marginBottom: 16,
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        textAlign: 'center',
        marginBottom: 16,
        fontSize: '1.1rem',
        fontFamily: 'var(--font-heading)',
        color: 'var(--text)',
      }}>
        {isTie ? 'The Council Could Not Agree' : 'The Village Has Spoken'}
      </div>

      {/* Vote breakdown */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
        {candidates.map(({ name, count, voters, isEliminated }) => (
          <div
            key={name}
            style={{
              padding: '10px 12px',
              borderRadius: 'var(--radius)',
              border: `1px solid ${isEliminated ? 'var(--danger)' : 'var(--border)'}`,
              background: isEliminated ? 'rgba(220, 38, 38, 0.08)' : 'var(--bg-elevated)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span style={{
                fontFamily: 'var(--font-heading)',
                fontSize: '0.95rem',
                color: isEliminated ? 'var(--danger)' : 'var(--text)',
              }}>
                {isEliminated ? '💀 ' : ''}{name}
              </span>
              <span style={{
                fontSize: '0.85rem',
                fontWeight: 600,
                color: 'var(--text-muted)',
              }}>
                {count} {count === 1 ? 'vote' : 'votes'}
              </span>
            </div>

            {/* Vote bar */}
            <div style={{
              height: 4,
              borderRadius: 2,
              background: 'var(--border)',
              marginBottom: 6,
              overflow: 'hidden',
            }}>
              <div style={{
                height: '100%',
                width: `${totalVotes > 0 ? (count / totalVotes) * 100 : 0}%`,
                background: isEliminated ? 'var(--danger)' : 'var(--accent)',
                borderRadius: 2,
                transition: 'width 0.6s ease',
              }} />
            </div>

            {/* Voter names */}
            {voters.length > 0 && (
              <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                Condemned by: {voters.join(', ')}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Outcome */}
      <div style={{
        textAlign: 'center',
        fontSize: '0.875rem',
        color: 'var(--text-muted)',
        fontStyle: 'italic',
        borderTop: '1px solid var(--border)',
        paddingTop: 12,
      }}>
        {isTie && (
          <div style={{ marginBottom: 4, fontSize: '0.75rem', color: 'var(--text-dim)' }}>
            The vote was tied. Fate chose...
          </div>
        )}
        <strong style={{ color: wasTraitor ? 'var(--accent)' : 'var(--danger)' }}>
          {eliminated}
        </strong>
        {' was cast out. They were '}
        {wasTraitor
          ? <strong style={{ color: 'var(--accent)' }}>the Shapeshifter!</strong>
          : <span>a <strong>{role ?? 'unknown role'}</strong>.</span>
        }
      </div>
    </div>
  )
}
