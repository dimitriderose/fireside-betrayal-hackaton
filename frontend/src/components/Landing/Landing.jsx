import { useNavigate } from 'react-router-dom'

// Full implementation delivered in feature/player-ui (P0-8)
export default function Landing() {
  const navigate = useNavigate()
  return (
    <div className="page" style={{ alignItems: 'center', justifyContent: 'center', padding: '60px 16px' }}>
      <div className="container" style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '4rem', marginBottom: '16px' }} className="fire-flicker">🔥</div>
        <h1 style={{ marginBottom: '8px' }}>Fireside: Betrayal</h1>
        <p style={{ marginBottom: '32px', fontSize: '1.125rem', fontStyle: 'italic' }}>
          The AI is one of you. Trust no one.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <button className="btn btn-primary btn-lg" onClick={() => navigate('/join?host=true')}>
            🔥 Create Game
          </button>
          <button className="btn btn-ghost btn-lg" onClick={() => navigate('/join')}>
            Join Game
          </button>
        </div>
      </div>
    </div>
  )
}
