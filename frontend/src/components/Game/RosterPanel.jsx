// ── Character roster — desktop sidebar + mobile icon strip ──────────────────
// Named exports only: import { RosterIconStrip, RosterSidebar } from './RosterPanel.jsx'

function buildCharacterList(players = [], myCharacterName, aiCharacters = []) {
  const all = (players || [])
    .map(p => ({ name: p.characterName, alive: p.alive }))
    .filter(c => c.name)
  for (const ai of aiCharacters) {
    if (ai?.name) all.push({ name: ai.name, alive: ai.alive === true })
  }
  return all
}

function shortName(name) {
  return name.split(' ').slice(0, 2).join(' ')
}

function icon(c, isMe) {
  return c.alive ? (isMe ? '🙂' : '🧑') : '💀'
}

// ── Mobile: horizontal icon strip ───────────────────────────────────────────

export function RosterIconStrip({ players, myCharacterName, aiCharacters }) {
  const all = buildCharacterList(players, myCharacterName, aiCharacters)
  if (all.length === 0) return null

  return (
    <div className="roster-strip">
      {all.map(c => {
        const isMe = c.name === myCharacterName
        const cls = [
          'roster-strip-icon',
          isMe && 'roster-strip-icon--me',
          !c.alive && 'roster-strip-icon--dead',
        ].filter(Boolean).join(' ')
        return (
          <div key={c.name} className={cls} title={shortName(c.name)}>
            {icon(c, isMe)}
          </div>
        )
      })}
    </div>
  )
}

// ── Desktop: vertical sidebar ───────────────────────────────────────────────

export function RosterSidebar({ players, myCharacterName, aiCharacters }) {
  const all = buildCharacterList(players, myCharacterName, aiCharacters)
  if (all.length === 0) return null

  return (
    <aside className="roster-sidebar">
      <div className="roster-sidebar-title">
        {all.filter(c => c.alive).length} of {all.length} alive
      </div>
      {all.map(c => {
        const isMe = c.name === myCharacterName
        const cls = [
          'roster-sidebar-item',
          isMe && 'roster-sidebar-item--me',
          !c.alive && 'roster-sidebar-item--dead',
        ].filter(Boolean).join(' ')
        return (
          <div key={c.name} className={cls}>
            <span className="roster-sidebar-item__icon">{icon(c, isMe)}</span>
            <span className="roster-sidebar-item__name">{shortName(c.name)}</span>
          </div>
        )
      })}
    </aside>
  )
}
