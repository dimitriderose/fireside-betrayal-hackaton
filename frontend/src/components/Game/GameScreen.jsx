import { useParams } from 'react-router-dom'
import { useGame } from '../../context/GameContext.jsx'
import { useWebSocket } from '../../hooks/useWebSocket.js'
import VotePanel from '../Voting/VotePanel.jsx'

const PHASE_LABELS = {
  setup: 'Gathering',
  night: '🌙 Night',
  day_discussion: '☀ Discussion',
  day_vote: '⚖ Vote',
  elimination: '⚰ Verdict',
  game_over: 'Game Over',
}

const PHASE_CLASS = {
  night: 'phase-night',
  day_discussion: 'phase-day',
  day_vote: 'phase-vote',
  elimination: 'phase-elimination',
}

/**
 * GameScreen — main in-game screen.
 *
 * P0-7 delivers: WebSocket connection, VotePanel during day_vote, phase header.
 * Full game interface (narrator audio, chat, night actions, role card) delivered in P0-8.
 */
export default function GameScreen() {
  const { gameId } = useParams()
  const { state } = useGame()
  const { playerId, phase, characterName, round, connected, role, isEliminated } = state
  const { connectionStatus, sendMessage } = useWebSocket(gameId, playerId)

  return (
    <div className="page">

      {/* ── Sticky phase header ── */}
      <div
        style={{
          background: 'var(--bg-card)',
          borderBottom: '1px solid var(--border)',
          padding: '10px 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'sticky',
          top: 0,
          zIndex: 10,
        }}
      >
        {/* Character + round */}
        <div>
          <div
            style={{
              fontFamily: 'var(--font-heading)',
              fontSize: '0.9375rem',
              color: 'var(--accent)',
              fontWeight: 600,
            }}
          >
            {characterName ?? '…'}
          </div>
          {round > 0 && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Round {round}
            </div>
          )}
        </div>

        {/* Phase pill */}
        <span className={`phase-indicator ${PHASE_CLASS[phase] ?? 'phase-day'}`}>
          {PHASE_LABELS[phase] ?? phase}
        </span>

        {/* Connection dot */}
        <div
          title={connectionStatus}
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: connectionStatus === 'connected' ? 'var(--success)' : 'var(--danger)',
            flexShrink: 0,
          }}
        />
      </div>

      {/* ── Main content area ── */}
      <div style={{ flex: 1, paddingBottom: 32 }}>

        {/* Day vote phase: full VotePanel */}
        {phase === 'day_vote' && (
          <VotePanel sendMessage={sendMessage} />
        )}

        {/* All other phases: placeholder until P0-8 */}
        {phase !== 'day_vote' && (
          <div
            className="container"
            style={{ paddingTop: 48, paddingBottom: 32, textAlign: 'center' }}
          >
            {/* Role badge */}
            {role && (
              <div style={{ marginBottom: 24 }}>
                <span className={`badge badge-accent role-${role}`} style={{ fontSize: '0.875rem', padding: '6px 16px' }}>
                  {role.charAt(0).toUpperCase() + role.slice(1)}
                </span>
              </div>
            )}

            {/* Phase description */}
            <div style={{ color: 'var(--text-muted)', marginBottom: 8 }}>
              {phase === 'night' && '🌙 The village sleeps…'}
              {phase === 'day_discussion' && '☀ The village awakens. Discuss.'}
              {phase === 'elimination' && '⚰ The verdict is delivered…'}
              {phase === 'game_over' && '🔥 The story ends.'}
              {phase === 'setup' && 'Waiting for the game to begin…'}
            </div>

            {isEliminated && (
              <p style={{ marginTop: 16, fontSize: '0.875rem', color: 'var(--text-dim)' }}>
                You have been eliminated from Thornwood.
              </p>
            )}

            <p
              style={{
                marginTop: 32,
                fontSize: '0.75rem',
                color: 'var(--text-dim)',
              }}
            >
              Full interface coming in P0-8 (narrator audio, chat, night actions)
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
