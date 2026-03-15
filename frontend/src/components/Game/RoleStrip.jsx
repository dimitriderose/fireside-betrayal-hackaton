import { useState } from 'react'

// ── Role reminder text (§12.3.6) ──────────────────────────────────────────────

const ROLE_REMINDERS = {
  villager:     'You have no special abilities. Survive by identifying the Shapeshifter through discussion and voting.',
  seer:         "Each night, choose one character to investigate. You'll learn if they are the Shapeshifter or not.",
  healer:       'Each night, choose one character to protect. If the Shapeshifter targets them, they survive.',
  hunter:       'When you are eliminated, you immediately choose one other character to take with you. Use it wisely.',
  drunk:        "Each night, choose one character to investigate. You'll learn if they are the Shapeshifter or not.",
  bodyguard:    'Each night, protect one character. If the Shapeshifter targets them, you die instead.',
  tanner:       'You win only if YOU are voted out. Act suspicious — make them vote for you.',
  shapeshifter: 'Each night, choose one character to eliminate. Blend in during the day to avoid detection.',
}

const ROLE_ICONS = {
  villager:     '🧑‍🌾',
  seer:         '🔮',
  healer:       '💚',
  hunter:       '🏹',
  drunk:        '🔮',
  bodyguard:    '🛡️',
  tanner:       '🪓',
  shapeshifter: '🐺',
}

const ROLE_LABELS = {
  villager:     'Villager',
  seer:         'Seer',
  healer:       'Healer',
  hunter:       'Hunter',
  drunk:        'Seer',
  bodyguard:    'Bodyguard',
  tanner:       'Tanner',
  shapeshifter: 'Shapeshifter',
}

// ── RoleStrip component ────────────────────────────────────────────────────────

/**
 * Persistent bottom bar that shows the player's role icon + name.
 * Tapping expands to reveal the full ability reminder text.
 *
 * Props:
 *   role          {string}  – role key (e.g. 'seer', 'villager')
 *   characterName {string}  – the player's in-game character name
 */
export default function RoleStrip({ role, characterName }) {
  const [expanded, setExpanded] = useState(false)

  if (!role) return null

  const icon    = ROLE_ICONS[role]  ?? '❓'
  const label   = ROLE_LABELS[role] ?? role
  const reminder = ROLE_REMINDERS[role] ?? 'Your secret role in Thornwood.'

  return (
    <div className={`role-strip${expanded ? ' role-strip-expanded' : ''}`}>
      <button
        className="role-strip-trigger"
        onClick={() => setExpanded(prev => !prev)}
        aria-expanded={expanded}
        aria-label={`${label} role details`}
      >
        <div className="role-strip-identity">
          <span className="role-strip-icon" aria-hidden="true">{icon}</span>
          <div className="role-strip-names">
            <span className="role-strip-character">{characterName ?? 'Your Character'}</span>
            <span className="role-strip-label">{label}</span>
          </div>
        </div>
        <span className="role-strip-chevron" aria-hidden="true">
          {expanded ? '▼' : '▲'}
        </span>
      </button>

      {expanded && (
        <div className="role-reminder-panel fade-in" role="note">
          <p className="role-reminder-text">{reminder}</p>
        </div>
      )}
    </div>
  )
}
