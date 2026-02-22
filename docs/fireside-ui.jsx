import { useState, useEffect, useRef } from "react";

// ============================================================
// FIRESIDE: BETRAYAL — Mobile UI v3
// v2 → v3 changes:
// ✓ Role strip hides when target picker is open (max 4 bottom rows)
// ✓ Chat input disabled during night phase ("Night has fallen...")
// ✓ New message indicator dot on story log bottom edge
// ✓ Narrator dramatic context line on vote screen
// ✓ Warmer narrator sign-off above Play Again button
// Designer pushback: build order should be Join → Game → Vote → End
// ============================================================

const P = {
  void: "#0a0908",
  night: "#0f1117",
  charcoal: "#1a1c24",
  slate: "#252831",
  ash: "#3a3d48",
  smoke: "#6b7080",
  bone: "#d4c5a9",
  parchment: "#e8dcc8",
  ember: "#e8652b",
  flame: "#f09030",
  gold: "#d4a24e",
  crimson: "#c42b2b",
  green: "#2d6b4f",
  teal: "#3a8a7a",
  nightBlue: "#1c2541",
};

const CHR_COLORS = {
  "Blacksmith Garin": "#c97d4a",
  "Merchant Elara": "#7ab6a3",
  "Scholar Theron": "#8b8cc7",
  "Herbalist Mira": "#7dba6f",
  "Brother Aldric": "#c9a84c",
};

const CHR_ICONS = {
  "Blacksmith Garin": "⚒️",
  "Merchant Elara": "💰",
  "Scholar Theron": "📜",
  "Herbalist Mira": "🌿",
  "Brother Aldric": "⛪",
};

// ─── Shared Components ───────────────────────────────────────

const Fireflies = () => {
  const ps = Array.from({ length: 10 }, (_, i) => ({
    id: i, l: Math.random() * 100, t: 20 + Math.random() * 70,
    d: Math.random() * 5, dur: 3 + Math.random() * 4, s: 2 + Math.random() * 2,
  }));
  return (
    <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0, overflow: "hidden" }}>
      {ps.map((p) => (
        <div key={p.id} style={{
          position: "absolute", left: `${p.l}%`, top: `${p.t}%`,
          width: p.s, height: p.s, borderRadius: "50%",
          background: P.flame, boxShadow: `0 0 ${p.s * 3}px ${P.flame}80`,
          opacity: 0, animation: `firefly ${p.dur}s ${p.d}s ease-in-out infinite`,
        }} />
      ))}
    </div>
  );
};

const EmberDivider = () => (
  <div style={{
    height: 1, margin: "16px 0",
    background: `linear-gradient(90deg, transparent, ${P.ember}60, ${P.flame}40, ${P.ember}60, transparent)`,
  }} />
);

const CharacterStrip = ({ characters }) => (
  <div style={{
    display: "flex", gap: 3, padding: "6px 10px", overflowX: "auto",
    borderBottom: `1px solid ${P.ash}20`, background: `${P.charcoal}90`,
    scrollbarWidth: "none", flexShrink: 0,
  }}>
    {characters.map((ch) => {
      const col = CHR_COLORS[ch.name] || P.bone;
      return (
        <div key={ch.name} style={{
          display: "flex", alignItems: "center", gap: 4, flexShrink: 0,
          padding: "4px 8px", borderRadius: 14,
          opacity: ch.alive ? 1 : 0.3, transition: "all 0.2s",
        }}>
          <span style={{ fontSize: 12 }}>{ch.alive ? (CHR_ICONS[ch.name] || "👤") : "💀"}</span>
          <span style={{
            fontSize: 9, fontFamily: "'Courier New', monospace",
            color: ch.isYou ? P.gold : col, fontWeight: ch.isYou ? 700 : 400,
            whiteSpace: "nowrap",
          }}>
            {ch.name.split(" ").pop()}{ch.isYou ? " (you)" : ""}
          </span>
        </div>
      );
    })}
  </div>
);

// ─── Screen 1: Join / Lobby ──────────────────────────────────

const JoinScreen = ({ onStart }) => {
  const [tab, setTab] = useState("join");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [difficulty, setDifficulty] = useState("normal");
  const players = [
    { name: "Dimitri", ready: true },
    { name: "Sarah", ready: true },
    { name: "Jake", ready: true },
    { name: "Maria", ready: false },
  ];

  return (
    <div style={{ minHeight: "100vh", background: P.void, position: "relative", overflow: "hidden" }}>
      <Fireflies />
      <div style={{
        position: "fixed", bottom: -80, left: "50%", transform: "translateX(-50%)",
        width: 500, height: 350, borderRadius: "50%",
        background: `radial-gradient(ellipse, ${P.ember}20, ${P.flame}10, transparent 65%)`,
        pointerEvents: "none",
      }} />

      <div style={{ position: "relative", zIndex: 1, padding: "48px 24px 40px" }}>
        <div style={{ textAlign: "center", marginBottom: 36 }}>
          <div style={{ fontSize: 44, marginBottom: 6 }}>🔥</div>
          <h1 style={{
            fontFamily: "'Georgia', serif", fontSize: 28, fontWeight: 400,
            color: P.parchment, letterSpacing: 4, margin: 0, textTransform: "uppercase",
          }}>Fireside</h1>
          <div style={{
            fontFamily: "'Courier New', monospace", fontSize: 10, color: P.ember,
            letterSpacing: 6, marginTop: 4, textTransform: "uppercase",
          }}>Betrayal</div>
          <p style={{
            fontFamily: "'Georgia', serif", fontSize: 13, color: P.smoke,
            fontStyle: "italic", marginTop: 14,
          }}>The AI is one of you. Trust no one.</p>
        </div>

        {tab === "join" ? (
          <div style={{ maxWidth: 320, margin: "0 auto" }}>
            <div style={{ marginBottom: 18 }}>
              <label style={{ display: "block", fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke, letterSpacing: 2, textTransform: "uppercase", marginBottom: 6 }}>Your Name</label>
              <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Enter your name"
                style={{ width: "100%", padding: "13px 14px", background: P.charcoal, border: `1px solid ${P.ash}`, borderRadius: 8, color: P.parchment, fontSize: 14, fontFamily: "'Georgia', serif", outline: "none", boxSizing: "border-box" }} />
            </div>
            <div style={{ marginBottom: 24 }}>
              <label style={{ display: "block", fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke, letterSpacing: 2, textTransform: "uppercase", marginBottom: 6 }}>Game Code</label>
              <input type="text" value={code} onChange={(e) => setCode(e.target.value.toUpperCase().slice(0, 4))} placeholder="XXXX" maxLength={4}
                style={{ width: "100%", padding: "13px", background: P.charcoal, border: `1px solid ${P.ash}`, borderRadius: 8, color: P.flame, fontSize: 28, fontFamily: "'Courier New', monospace", letterSpacing: 14, textAlign: "center", outline: "none", boxSizing: "border-box" }} />
            </div>
            <button onClick={() => { if (name.trim()) setTab("lobby"); }}
              disabled={!name.trim()}
              style={{ width: "100%", padding: "15px", background: name.trim() ? `linear-gradient(135deg, ${P.ember}, ${P.flame})` : P.charcoal, border: "none", borderRadius: 8, color: name.trim() ? P.void : P.smoke, fontSize: 13, fontFamily: "'Courier New', monospace", fontWeight: 700, letterSpacing: 3, textTransform: "uppercase", cursor: name.trim() ? "pointer" : "default", boxShadow: name.trim() ? `0 4px 20px ${P.ember}40` : "none" }}>
              Join Game
            </button>
            <EmberDivider />
            <button onClick={() => setTab("lobby")}
              style={{ width: "100%", padding: "13px", background: "transparent", border: `1px solid ${P.ash}`, borderRadius: 8, color: P.bone, fontSize: 10, fontFamily: "'Courier New', monospace", letterSpacing: 2, textTransform: "uppercase", cursor: "pointer" }}>
              Create New Game
            </button>
          </div>
        ) : (
          <div style={{ maxWidth: 320, margin: "0 auto" }}>
            <div style={{ textAlign: "center", padding: "14px", background: P.charcoal, borderRadius: 8, marginBottom: 20, border: `1px solid ${P.ash}` }}>
              <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke, letterSpacing: 2, textTransform: "uppercase", marginBottom: 4 }}>Share This Code</div>
              <div style={{ fontFamily: "'Courier New', monospace", fontSize: 34, color: P.flame, letterSpacing: 16, fontWeight: 700 }}>7R4F</div>
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: "block", fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke, letterSpacing: 2, textTransform: "uppercase", marginBottom: 8 }}>AI Deception Level</label>
              <div style={{ display: "flex", gap: 6 }}>
                {[
                  { key: "easy", label: "Easy", desc: "Makes mistakes" },
                  { key: "normal", label: "Normal", desc: "Competent" },
                  { key: "hard", label: "Hard", desc: "Ruthless" },
                ].map((d) => (
                  <button key={d.key} onClick={() => setDifficulty(d.key)} style={{
                    flex: 1, padding: "9px 4px",
                    background: difficulty === d.key ? `${P.ember}20` : P.charcoal,
                    border: `1px solid ${difficulty === d.key ? P.ember : P.ash}`,
                    borderRadius: 8, cursor: "pointer", transition: "all 0.2s",
                  }}>
                    <div style={{ fontSize: 13, fontFamily: "'Georgia', serif", color: difficulty === d.key ? P.flame : P.bone, fontWeight: 600 }}>{d.label}</div>
                    <div style={{ fontSize: 9, fontFamily: "'Courier New', monospace", color: P.smoke, marginTop: 2 }}>{d.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Semi-circular player arrangement */}
            <div style={{ marginBottom: 22 }}>
              <label style={{ display: "block", fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke, letterSpacing: 2, textTransform: "uppercase", marginBottom: 12, textAlign: "center" }}>Around the Fire ({players.length}/6)</label>
              <div style={{ position: "relative", width: "100%", height: 180, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <div style={{
                  position: "absolute", bottom: 10, left: "50%", transform: "translateX(-50%)",
                  width: 50, height: 50, borderRadius: "50%",
                  background: `radial-gradient(circle, ${P.flame}50, ${P.ember}30, transparent 70%)`,
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 24,
                }}>🔥</div>
                {players.map((p, i) => {
                  const total = players.length;
                  const angle = Math.PI * (0.15 + (0.7 * i) / Math.max(total - 1, 1));
                  const rx = 120, ry = 70;
                  const x = 50 + rx * Math.cos(angle);
                  const y = 140 - ry * Math.sin(angle);
                  return (
                    <div key={i} style={{
                      position: "absolute", left: x - 28, top: y - 28,
                      width: 56, textAlign: "center",
                      animation: `fadeUp 0.4s ${i * 0.1}s both`,
                    }}>
                      <div style={{
                        width: 40, height: 40, borderRadius: "50%", margin: "0 auto 4px",
                        background: `linear-gradient(135deg, ${P.slate}, ${P.ash})`,
                        border: `2px solid ${i === 0 ? P.gold : p.ready ? P.green : P.ash}`,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 16, boxShadow: i === 0 ? `0 0 10px ${P.gold}30` : "none",
                      }}>🔥</div>
                      <div style={{ fontSize: 10, fontFamily: "'Courier New', monospace", color: P.bone, lineHeight: 1.2 }}>{p.name}</div>
                      {i === 0 && <div style={{ fontSize: 8, fontFamily: "'Courier New', monospace", color: P.gold, letterSpacing: 1 }}>HOST</div>}
                    </div>
                  );
                })}
                <div style={{
                  position: "absolute", right: 15, top: 30,
                  width: 40, height: 40, borderRadius: "50%",
                  border: `1px dashed ${P.ash}`, display: "flex",
                  alignItems: "center", justifyContent: "center",
                }}>
                  <span style={{ fontSize: 9, color: P.smoke, fontFamily: "'Courier New', monospace" }}>+</span>
                </div>
              </div>
            </div>

            <button onClick={onStart} style={{
              width: "100%", padding: "15px",
              background: `linear-gradient(135deg, ${P.ember}, ${P.flame})`,
              border: "none", borderRadius: 8, color: P.void,
              fontSize: 13, fontFamily: "'Courier New', monospace", fontWeight: 700,
              letterSpacing: 3, textTransform: "uppercase", cursor: "pointer",
              boxShadow: `0 4px 20px ${P.ember}40`,
            }}>Begin the Story</button>
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Screen 2: Main Game ─────────────────────────────────────

const GameScreen = ({ onVote }) => {
  const [phase, setPhase] = useState("day");
  const [showNightAction, setShowNightAction] = useState(false);
  const [nightTarget, setNightTarget] = useState(null);
  const [showRoleFull, setShowRoleFull] = useState(false);
  const [reactionMode, setReactionMode] = useState(null);
  const [reactionTarget, setReactionTarget] = useState(null);
  const [showNewMsg, setShowNewMsg] = useState(true);
  const logRef = useRef(null);

  const characters = [
    { name: "Blacksmith Garin", alive: true },
    { name: "Merchant Elara", alive: true, isYou: true },
    { name: "Scholar Theron", alive: false },
    { name: "Herbalist Mira", alive: true },
    { name: "Brother Aldric", alive: true },
  ];
  const alive = characters.filter((c) => c.alive && !c.isYou);

  const storyLog = [
    { speaker: "Narrator", text: "Dawn breaks over Thornwood. The village stirs, but unease hangs thick as morning fog. Scholar Theron was found cold and still in his study, a look of terror frozen on his face.", type: "narrator" },
    { speaker: "Blacksmith Garin", text: "I was at the forge all night. The coals don't tend themselves.", type: "character" },
    { speaker: "Narrator", text: "The Blacksmith's hands are steady, but his eyes betray something — a flicker of calculation behind the concern.", type: "narrator" },
    { speaker: "Herbalist Mira", text: "Has anyone checked the well? I heard footsteps near the square well past midnight.", type: "character" },
    { speaker: "Brother Aldric", text: "I was praying in the chapel. I heard nothing. Perhaps that itself is suspicious — one would expect to hear something on a night like this.", type: "character" },
    { speaker: "Narrator", text: "The village falls silent. All eyes turn to one another. Five remain at the fire. One of you is not what they seem.", type: "narrator" },
  ];

  const isNight = phase === "night";
  // v3: hide role strip when target picker is active (reduce bottom chrome)
  const showRoleStrip = !reactionMode;

  return (
    <div style={{ height: "100vh", background: P.void, display: "flex", flexDirection: "column", position: "relative" }}>
      {/* Night overlay */}
      <div style={{
        position: "fixed", inset: 0, background: P.nightBlue,
        opacity: isNight ? 0.45 : 0, transition: "opacity 1.5s ease",
        pointerEvents: "none", zIndex: 2,
      }} />

      {/* Header */}
      <div style={{
        padding: "8px 12px", display: "flex", alignItems: "center", justifyContent: "space-between",
        borderBottom: `1px solid ${P.ash}25`, zIndex: 3, flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 14 }}>🔥</span>
          <span style={{ fontFamily: "'Georgia', serif", fontSize: 13, color: P.parchment }}>Fireside</span>
        </div>
        <div style={{
          display: "flex", alignItems: "center", gap: 5, padding: "3px 10px",
          borderRadius: 14, background: isNight ? `${P.nightBlue}60` : `${P.flame}12`,
          border: `1px solid ${isNight ? P.nightBlue : P.flame}30`,
        }}>
          <span style={{ fontSize: 10 }}>{isNight ? "🌙" : "☀️"}</span>
          <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: isNight ? P.teal : P.flame, letterSpacing: 1, textTransform: "uppercase" }}>
            {isNight ? "Night" : "Day"} · R2
          </span>
        </div>
        <button onClick={() => { const next = isNight ? "day" : "night"; setPhase(next); if (next === "night") setShowNightAction(true); }}
          style={{ background: "none", border: "none", color: P.smoke, fontSize: 10, fontFamily: "'Courier New', monospace", cursor: "pointer", padding: "3px 6px" }}>◐</button>
      </div>

      {/* Character Strip */}
      <CharacterStrip characters={characters} />

      {/* Story Log — DOMINANT */}
      <div ref={logRef} onScroll={() => setShowNewMsg(false)} style={{
        flex: 1, overflow: "auto", padding: "12px 14px", zIndex: 3,
        display: "flex", flexDirection: "column", gap: 10, position: "relative",
      }}>
        {storyLog.map((msg, i) => (
          <div key={i} style={{ animation: `fadeUp 0.4s ${i * 0.08}s both` }}>
            {msg.type === "narrator" ? (
              <div style={{
                padding: "12px 14px",
                background: `linear-gradient(135deg, ${P.charcoal}, ${P.slate}60)`,
                borderRadius: 10, borderLeft: `3px solid ${P.ember}`,
                boxShadow: `inset 0 0 20px ${P.void}40`,
              }}>
                <div style={{
                  fontFamily: "'Courier New', monospace", fontSize: 9,
                  color: P.ember, letterSpacing: 2, textTransform: "uppercase", marginBottom: 5,
                  display: "flex", alignItems: "center", gap: 4,
                }}>
                  <span style={{ fontSize: 8 }}>🔥</span> Narrator
                </div>
                <div style={{
                  fontFamily: "'Georgia', serif", fontSize: 13.5,
                  color: P.parchment, lineHeight: 1.65, fontStyle: "italic",
                }}>{msg.text}</div>
              </div>
            ) : (
              <div style={{ paddingLeft: 8 }}>
                <div style={{
                  fontFamily: "'Courier New', monospace", fontSize: 10,
                  color: CHR_COLORS[msg.speaker] || P.bone,
                  marginBottom: 3, fontWeight: 700, letterSpacing: 0.5,
                  display: "flex", alignItems: "center", gap: 4,
                }}>
                  <span style={{ fontSize: 10 }}>{CHR_ICONS[msg.speaker] || "👤"}</span>
                  {msg.speaker}
                </div>
                <div style={{
                  fontFamily: "'Georgia', serif", fontSize: 13,
                  color: `${P.bone}dd`, lineHeight: 1.5,
                  padding: "6px 10px",
                  background: `${P.charcoal}60`,
                  borderRadius: "2px 10px 10px 10px",
                }}>"{msg.text}"</div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* v3: New message indicator */}
      {showNewMsg && (
        <div style={{
          position: "relative", zIndex: 4, display: "flex", justifyContent: "center",
          marginTop: -16, marginBottom: 4, pointerEvents: "none",
        }}>
          <div style={{
            padding: "2px 10px", borderRadius: 10,
            background: P.ember, fontSize: 9,
            fontFamily: "'Courier New', monospace", color: P.void,
            fontWeight: 700, letterSpacing: 1,
            animation: "fadeUp 0.3s ease",
          }}>
            ↓ new
          </div>
        </div>
      )}

      {/* v3: Role strip — hidden when target picker is open */}
      {showRoleStrip && (
        <div onClick={() => setShowRoleFull(true)} style={{
          padding: "6px 14px", display: "flex", alignItems: "center", gap: 8,
          background: P.charcoal, borderTop: `1px solid ${P.gold}25`,
          cursor: "pointer", zIndex: 3, flexShrink: 0,
          transition: "all 0.2s ease",
        }}>
          <span style={{ fontSize: 14 }}>💰</span>
          <div style={{ flex: 1 }}>
            <span style={{ fontFamily: "'Georgia', serif", fontSize: 13, color: P.parchment }}>Merchant Elara</span>
            <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.teal, marginLeft: 8, letterSpacing: 1 }}>★ HEALER</span>
          </div>
          <span style={{ fontSize: 9, color: P.smoke }}>▲</span>
        </div>
      )}

      {/* Quick Reactions — hidden during night */}
      {!isNight && (
        <div style={{
          padding: "6px 10px", display: "flex", gap: 4, overflowX: "auto",
          borderTop: `1px solid ${P.ash}15`, zIndex: 3, flexShrink: 0,
          scrollbarWidth: "none",
        }}>
          {[
            { emoji: "🔍", label: "I suspect...", key: "suspect", targeting: true },
            { emoji: "🤝", label: "I trust...", key: "trust", targeting: true },
            { emoji: "👍", label: "I agree", key: "agree", targeting: false },
            { emoji: "💡", label: "I know something", key: "info", targeting: false },
          ].map((r) => (
            <button key={r.key} onClick={() => {
              if (r.targeting) {
                setReactionMode(reactionMode === r.key ? null : r.key);
                setReactionTarget(null);
              } else {
                setReactionMode(null);
              }
            }} style={{
              flexShrink: 0, padding: "6px 10px",
              background: reactionMode === r.key ? `${P.ember}20` : P.charcoal,
              border: `1px solid ${reactionMode === r.key ? P.ember : P.ash}60`,
              borderRadius: 16, display: "flex", alignItems: "center", gap: 4,
              cursor: "pointer", transition: "all 0.2s",
            }}>
              <span style={{ fontSize: 11 }}>{r.emoji}</span>
              <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: reactionMode === r.key ? P.flame : P.bone, whiteSpace: "nowrap" }}>{r.label}</span>
            </button>
          ))}
        </div>
      )}

      {/* Character Target Picker */}
      {reactionMode && (
        <div style={{
          padding: "6px 10px", display: "flex", gap: 4, overflowX: "auto",
          background: P.charcoal, borderTop: `1px solid ${P.ember}20`,
          zIndex: 3, flexShrink: 0, scrollbarWidth: "none",
          animation: "fadeUp 0.2s ease",
        }}>
          <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke, alignSelf: "center", marginRight: 4, whiteSpace: "nowrap" }}>Who?</span>
          {alive.map((ch) => (
            <button key={ch.name} onClick={() => { setReactionTarget(ch.name); setTimeout(() => { setReactionMode(null); setReactionTarget(null); }, 600); }}
              style={{
                flexShrink: 0, padding: "5px 10px", display: "flex", alignItems: "center", gap: 4,
                background: reactionTarget === ch.name ? (reactionMode === "suspect" ? `${P.crimson}25` : `${P.green}25`) : P.slate,
                border: `1px solid ${reactionTarget === ch.name ? (reactionMode === "suspect" ? P.crimson : P.green) : P.ash}50`,
                borderRadius: 14, cursor: "pointer", transition: "all 0.15s",
              }}>
              <span style={{ fontSize: 10 }}>{CHR_ICONS[ch.name]}</span>
              <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.bone }}>{ch.name.split(" ").pop()}</span>
            </button>
          ))}
        </div>
      )}

      {/* v3: Chat Input — disabled during night phase */}
      <div style={{ padding: "8px 12px 16px", display: "flex", gap: 6, zIndex: 3, flexShrink: 0 }}>
        <input type="text"
          disabled={isNight}
          placeholder={isNight ? "Night has fallen... await the dawn" : "Speak as Merchant Elara..."}
          style={{
            flex: 1, padding: "11px 14px",
            background: isNight ? P.night : P.charcoal,
            border: `1px solid ${isNight ? P.nightBlue + "40" : P.ash}`,
            borderRadius: 20, fontSize: 13, fontFamily: "'Georgia', serif", outline: "none",
            color: isNight ? P.smoke : P.parchment,
            fontStyle: isNight ? "italic" : "normal",
            cursor: isNight ? "default" : "text",
            transition: "all 0.5s ease",
          }} />
        <button onClick={isNight ? undefined : onVote}
          disabled={isNight}
          style={{
            width: 42, height: 42, borderRadius: "50%",
            background: isNight ? P.ash : `linear-gradient(135deg, ${P.ember}, ${P.flame})`,
            border: "none", color: isNight ? P.smoke : P.void, fontSize: 14,
            cursor: isNight ? "default" : "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: isNight ? "none" : `0 2px 10px ${P.ember}30`,
            transition: "all 0.5s ease",
          }}>↗</button>
      </div>

      {/* Night Phase Action Modal */}
      {showNightAction && (
        <div style={{ position: "fixed", inset: 0, zIndex: 20 }}>
          <div style={{ position: "absolute", inset: 0, background: `${P.void}90`, backdropFilter: "blur(4px)" }} />
          <div style={{
            position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)",
            width: "calc(100% - 48px)", maxWidth: 340,
            background: P.charcoal, borderRadius: 16,
            border: `1px solid ${P.teal}30`, overflow: "hidden",
            animation: "fadeUp 0.3s ease",
          }}>
            <div style={{ height: 4, background: `linear-gradient(90deg, transparent, ${P.teal}60, transparent)` }} />
            <div style={{ padding: "24px 20px" }}>
              <div style={{ textAlign: "center", marginBottom: 20 }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>🌙</div>
                <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.teal, letterSpacing: 3, textTransform: "uppercase", marginBottom: 6 }}>Night Phase · Healer</div>
                <div style={{ fontFamily: "'Georgia', serif", fontSize: 18, color: P.parchment }}>Choose one to protect</div>
                <p style={{ fontFamily: "'Georgia', serif", fontSize: 13, color: P.smoke, fontStyle: "italic", marginTop: 8, lineHeight: 1.5 }}>
                  Your healing gifts can shield one soul from the Shapeshifter's grasp tonight.
                </p>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {alive.map((ch) => (
                  <button key={ch.name} onClick={() => setNightTarget(ch.name)} style={{
                    display: "flex", alignItems: "center", gap: 12, padding: "14px 16px",
                    background: nightTarget === ch.name ? `${P.teal}15` : P.slate,
                    border: `1.5px solid ${nightTarget === ch.name ? P.teal : P.ash}`,
                    borderRadius: 10, cursor: "pointer", textAlign: "left",
                    transition: "all 0.2s",
                    boxShadow: nightTarget === ch.name ? `0 0 15px ${P.teal}10` : "none",
                  }}>
                    <div style={{
                      width: 40, height: 40, borderRadius: 8,
                      background: `linear-gradient(135deg, ${P.charcoal}, ${P.slate})`,
                      display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
                      border: `1px solid ${nightTarget === ch.name ? P.teal + "50" : P.ash}`,
                    }}>{CHR_ICONS[ch.name]}</div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontFamily: "'Georgia', serif", fontSize: 14, color: P.parchment }}>{ch.name}</div>
                    </div>
                    {nightTarget === ch.name && (
                      <div style={{
                        width: 22, height: 22, borderRadius: "50%",
                        background: P.teal, display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 11, color: "white", fontWeight: 700,
                      }}>✓</div>
                    )}
                  </button>
                ))}
              </div>
              <button onClick={() => { setShowNightAction(false); setPhase("day"); }} disabled={!nightTarget}
                style={{
                  width: "100%", marginTop: 16, padding: "14px",
                  background: nightTarget ? `linear-gradient(135deg, ${P.teal}, ${P.green})` : P.ash,
                  border: "none", borderRadius: 8, color: nightTarget ? "white" : P.smoke,
                  fontSize: 13, fontFamily: "'Courier New', monospace", fontWeight: 700,
                  letterSpacing: 2, textTransform: "uppercase", cursor: nightTarget ? "pointer" : "default",
                  boxShadow: nightTarget ? `0 4px 15px ${P.teal}30` : "none", transition: "all 0.3s",
                }}>
                Protect {nightTarget ? nightTarget.split(" ").pop() : "..."}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Full Role Card Drawer */}
      {showRoleFull && (
        <div style={{ position: "fixed", inset: 0, zIndex: 15 }}>
          <div onClick={() => setShowRoleFull(false)} style={{ position: "absolute", inset: 0, background: `${P.void}80` }} />
          <div style={{
            position: "absolute", bottom: 0, left: 0, right: 0,
            background: P.charcoal, borderTop: `2px solid ${P.gold}`,
            borderRadius: "16px 16px 0 0", padding: "20px 24px 32px",
            animation: "slideUp 0.3s ease",
          }}>
            <div style={{ width: 32, height: 3, borderRadius: 2, background: P.ash, margin: "0 auto 16px" }} />
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 36, marginBottom: 8 }}>💰</div>
              <div style={{ fontFamily: "'Georgia', serif", fontSize: 20, color: P.parchment }}>Merchant Elara</div>
              <div style={{ fontFamily: "'Courier New', monospace", fontSize: 10, color: P.teal, letterSpacing: 3, textTransform: "uppercase", marginTop: 4 }}>★ Healer ★</div>
              <EmberDivider />
              <p style={{ fontFamily: "'Georgia', serif", fontSize: 13, color: P.bone, lineHeight: 1.6, fontStyle: "italic", margin: 0 }}>
                Each night, choose one character to protect from the Shapeshifter. If you protect the right person, they survive. Choose wisely — you cannot protect yourself.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Screen 3: Vote ──────────────────────────────────────────

const VoteScreen = ({ onEliminate }) => {
  const [selected, setSelected] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [timer, setTimer] = useState(42);

  const candidates = [
    { name: "Blacksmith Garin", context: "Claimed to be at the forge — but no one can confirm.", votes: 2 },
    { name: "Herbalist Mira", context: "Heard footsteps by the well. First to speak at dawn.", votes: 0 },
    { name: "Brother Aldric", context: "Admits he heard nothing. Called his own silence suspicious.", votes: 1 },
  ];

  useEffect(() => {
    const i = setInterval(() => setTimer((t) => Math.max(0, t - 1)), 1000);
    return () => clearInterval(i);
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: P.void, display: "flex", flexDirection: "column", position: "relative" }}>
      <div style={{ position: "fixed", inset: 0, background: `radial-gradient(ellipse at top, ${P.crimson}08, transparent 50%)`, pointerEvents: "none" }} />

      <div style={{ position: "relative", zIndex: 1, flex: 1, display: "flex", flexDirection: "column", padding: "20px 18px" }}>
        <div style={{ textAlign: "center", marginBottom: 16 }}>
          <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.crimson, letterSpacing: 3, textTransform: "uppercase", marginBottom: 6 }}>⚖️ The Vote</div>
          <h2 style={{ fontFamily: "'Georgia', serif", fontSize: 20, color: P.parchment, fontWeight: 400, fontStyle: "italic", margin: 0 }}>Who do you cast out?</h2>

          {/* v3: Narrator dramatic context */}
          <p style={{
            fontFamily: "'Georgia', serif", fontSize: 12, color: P.smoke,
            fontStyle: "italic", marginTop: 8, lineHeight: 1.5, padding: "0 12px",
          }}>
            "The fire crackles low. Three names hang in the air like smoke. One of them is the creature wearing a villager's face. Choose wrong, and another innocent falls."
          </p>

          <div style={{
            marginTop: 14, display: "inline-flex", alignItems: "center", gap: 6,
            padding: "6px 18px", borderRadius: 20,
            background: timer < 15 ? `${P.crimson}20` : P.charcoal,
            border: `1px solid ${timer < 15 ? P.crimson : P.ash}`,
            transition: "all 0.3s",
          }}>
            <span style={{ fontSize: 12 }}>⏳</span>
            <span style={{
              fontFamily: "'Courier New', monospace", fontSize: 20,
              color: timer < 15 ? P.crimson : P.flame, fontWeight: 700,
            }}>0:{timer.toString().padStart(2, "0")}</span>
          </div>
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
          {candidates.map((c) => (
            <button key={c.name} onClick={() => !confirmed && setSelected(c.name)} style={{
              display: "flex", alignItems: "center", gap: 12, padding: "14px 16px",
              background: selected === c.name ? `linear-gradient(135deg, ${P.crimson}15, ${P.charcoal})` : P.charcoal,
              border: `2px solid ${selected === c.name ? P.crimson : P.ash}50`,
              borderRadius: 12, cursor: confirmed ? "default" : "pointer",
              textAlign: "left", transition: "all 0.2s",
              boxShadow: selected === c.name ? `0 0 16px ${P.crimson}10` : "none",
            }}>
              <div style={{
                width: 44, height: 44, borderRadius: 8, flexShrink: 0,
                background: `linear-gradient(135deg, ${P.slate}, ${P.ash})`,
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 20,
                border: `1px solid ${selected === c.name ? P.crimson + "50" : P.ash}`,
              }}>{CHR_ICONS[c.name]}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontFamily: "'Georgia', serif", fontSize: 14, color: selected === c.name ? P.parchment : P.bone }}>{c.name}</div>
                <div style={{ fontFamily: "'Georgia', serif", fontSize: 11, color: P.smoke, fontStyle: "italic", marginTop: 2, lineHeight: 1.3 }}>{c.context}</div>
              </div>
              <div>
                {selected === c.name ? (
                  <div style={{
                    width: 24, height: 24, borderRadius: "50%", background: P.crimson,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 12, color: "white", fontWeight: 700,
                  }}>✓</div>
                ) : (
                  <div style={{
                    padding: "2px 8px", borderRadius: 10,
                    background: c.votes > 0 ? `${P.crimson}20` : `${P.ash}40`,
                    border: `1px solid ${c.votes > 0 ? P.crimson + "30" : P.ash}`,
                  }}>
                    <span style={{
                      fontFamily: "'Courier New', monospace", fontSize: 10,
                      color: c.votes > 0 ? P.crimson : P.smoke, fontWeight: 700,
                    }}>{c.votes}</span>
                  </div>
                )}
              </div>
            </button>
          ))}
        </div>

        <div style={{
          marginTop: 12, padding: "8px 14px", background: P.charcoal, borderRadius: 8,
          border: `1px solid ${P.ash}25`, display: "flex", alignItems: "center", gap: 8,
        }}>
          <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke, letterSpacing: 1 }}>VOTES:</span>
          <div style={{ flex: 1, height: 4, background: P.ash, borderRadius: 2, overflow: "hidden" }}>
            <div style={{ width: "60%", height: "100%", background: `linear-gradient(90deg, ${P.crimson}, ${P.ember})`, borderRadius: 2, transition: "width 0.5s" }} />
          </div>
          <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke }}>3/5</span>
        </div>

        <button onClick={() => { if (selected && !confirmed) { setConfirmed(true); setTimeout(onEliminate, 1200); } }}
          disabled={!selected || confirmed}
          style={{
            marginTop: 12, width: "100%", padding: "15px",
            background: selected && !confirmed ? `linear-gradient(135deg, ${P.crimson}, ${P.ember})` : P.charcoal,
            border: "none", borderRadius: 8,
            color: selected && !confirmed ? "white" : P.smoke,
            fontSize: 13, fontFamily: "'Courier New', monospace", fontWeight: 700,
            letterSpacing: 3, textTransform: "uppercase",
            cursor: selected && !confirmed ? "pointer" : "default",
            boxShadow: selected && !confirmed ? `0 4px 16px ${P.crimson}35` : "none",
            transition: "all 0.3s",
          }}>
          {confirmed ? "Vote Cast..." : "Cast Your Vote"}
        </button>
      </div>
    </div>
  );
};

// ─── Screen 4: Game Over ─────────────────────────────────────

const GameOverScreen = ({ onRestart }) => {
  const [showTimeline, setShowTimeline] = useState(false);
  const [revealIdx, setRevealIdx] = useState(-1);

  const reveals = [
    { character: "Herbalist Mira", player: "Sarah", role: "Seer", icon: "🌿", roleIcon: "👁️", alive: true },
    { character: "Brother Aldric", player: "Jake", role: "Villager", icon: "⛪", roleIcon: "🏘️", alive: true },
    { character: "Merchant Elara", player: "Dimitri", role: "Healer", icon: "💰", roleIcon: "💚", alive: true, isYou: true },
    { character: "Scholar Theron", player: "Maria", role: "Hunter", icon: "📜", roleIcon: "🏹", alive: false, eliminatedRound: 1, revengeTarget: "Blacksmith Garin" },
    { character: "Blacksmith Garin", player: "THE AI", role: "Shapeshifter", icon: "⚒️", roleIcon: "🐺", alive: false, eliminatedRound: 1, isAI: true, killedBy: "Hunter's Revenge" },
  ];

  const timeline = [
    { round: 1, title: "Night 1", pub: "Scholar Theron found dead at dawn.", secret: "AI targeted Theron — the Hunter. Calculated gamble to remove a threat early.", reasoning: "Theron asked the most probing questions during introductions. Highest threat level." },
    { round: 2, title: "Night 2", pub: "Everyone survived. The Healer protected the right person.", secret: "AI targeted Herbalist Mira (the Seer), but Dimitri's Healer protected her.", reasoning: "Mira's investigation was getting close. Had to eliminate the Seer before she found me." },
    { round: 2, title: "The Final Vote", pub: "Village voted to eliminate Blacksmith Garin. But Theron's revenge killed him first.", secret: "AI attempted to frame Brother Aldric in final debate but Sarah's Seer intel was too strong.", reasoning: "Last-ditch effort. Built a coalition against Aldric — referenced his 'suspicious silence' from Round 1. Failed." },
  ];

  useEffect(() => {
    const i = setInterval(() => {
      setRevealIdx((prev) => {
        if (prev < reveals.length - 1) return prev + 1;
        clearInterval(i);
        return prev;
      });
    }, 600);
    return () => clearInterval(i);
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: P.void, position: "relative", overflow: "hidden" }}>
      <Fireflies />
      <div style={{
        position: "fixed", top: -50, left: "50%", transform: "translateX(-50%)",
        width: 500, height: 300, borderRadius: "50%",
        background: `radial-gradient(ellipse, ${P.gold}12, transparent 60%)`,
        pointerEvents: "none",
      }} />

      <div style={{ position: "relative", zIndex: 1, padding: "36px 18px 24px" }}>
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <div style={{ fontSize: 44, marginBottom: 8 }}>🏆</div>
          <h1 style={{ fontFamily: "'Georgia', serif", fontSize: 22, color: P.gold, fontWeight: 400, margin: 0 }}>The Village Triumphs</h1>
          <p style={{ fontFamily: "'Georgia', serif", fontSize: 13, color: P.smoke, fontStyle: "italic", marginTop: 8 }}>The shapeshifter has been unmasked and cast from Thornwood.</p>
        </div>

        <div style={{ marginBottom: 24 }}>
          <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke, letterSpacing: 2, textTransform: "uppercase", marginBottom: 10, paddingLeft: 2 }}>The Truth Revealed</div>
          {reveals.map((r, i) => (
            <div key={i} style={{
              display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", marginBottom: 5,
              borderRadius: 10,
              background: r.isAI ? `${P.crimson}12` : P.charcoal,
              border: `1px solid ${r.isAI ? P.crimson + "35" : P.ash + "25"}`,
              opacity: i <= revealIdx ? 1 : 0,
              transform: i <= revealIdx ? "translateX(0)" : "translateX(16px)",
              transition: "all 0.5s ease",
            }}>
              <div style={{
                width: 36, height: 36, borderRadius: 8, flexShrink: 0,
                background: r.isAI ? `linear-gradient(135deg, ${P.crimson}25, ${P.charcoal})` : `linear-gradient(135deg, ${P.slate}, ${P.ash})`,
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16,
                border: r.isAI ? `1px solid ${P.crimson}40` : "none",
              }}>{r.icon}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontFamily: "'Georgia', serif", fontSize: 13, color: P.parchment }}>{r.character}</div>
                <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: r.isAI ? P.crimson : P.smoke, marginTop: 1 }}>
                  was {r.player}
                  {!r.alive && <span style={{ color: P.smoke }}> · Eliminated R{r.eliminatedRound}</span>}
                  {r.revengeTarget && <span style={{ color: P.flame }}> · 🏹 Revenge → {r.revengeTarget.split(" ").pop()}</span>}
                  {r.killedBy && <span style={{ color: P.crimson }}> · 💀 {r.killedBy}</span>}
                </div>
              </div>
              <div style={{
                padding: "3px 8px", borderRadius: 10, flexShrink: 0,
                background: r.isAI ? `${P.crimson}20` : `${P.green}15`,
                border: `1px solid ${r.isAI ? P.crimson + "35" : P.green + "25"}`,
                display: "flex", alignItems: "center", gap: 3,
              }}>
                <span style={{ fontSize: 9 }}>{r.roleIcon}</span>
                <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: r.isAI ? P.crimson : P.teal, fontWeight: 600 }}>{r.role}</span>
              </div>
            </div>
          ))}
        </div>

        <button onClick={() => setShowTimeline(!showTimeline)} style={{
          width: "100%", padding: "12px", background: P.charcoal,
          border: `1px solid ${P.ember}35`, borderRadius: 10, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 6, marginBottom: 10,
        }}>
          <span style={{ fontSize: 13 }}>🧠</span>
          <span style={{ fontFamily: "'Courier New', monospace", fontSize: 10, color: P.flame, letterSpacing: 1, textTransform: "uppercase" }}>
            {showTimeline ? "Hide" : "Reveal"} AI Strategy
          </span>
          <span style={{ color: P.smoke, fontSize: 10 }}>{showTimeline ? "▲" : "▼"}</span>
        </button>

        {showTimeline && (
          <div style={{ marginBottom: 20 }}>
            {timeline.map((t, i) => (
              <div key={i} style={{
                padding: "12px 14px", marginBottom: 6, borderRadius: 10,
                background: P.charcoal, borderLeft: `3px solid ${P.ember}`,
                animation: `fadeUp 0.3s ${i * 0.12}s both`,
              }}>
                <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.ember, letterSpacing: 1, textTransform: "uppercase", marginBottom: 5 }}>
                  Round {t.round} — {t.title}
                </div>
                <div style={{ fontFamily: "'Georgia', serif", fontSize: 13, color: P.bone, lineHeight: 1.5, marginBottom: 8 }}>{t.pub}</div>
                <div style={{ padding: "7px 10px", background: `${P.crimson}08`, borderRadius: 6, border: `1px solid ${P.crimson}15`, marginBottom: 6 }}>
                  <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.crimson, letterSpacing: 1, marginBottom: 3 }}>🐺 HIDDEN</div>
                  <div style={{ fontFamily: "'Georgia', serif", fontSize: 12, color: P.parchment, lineHeight: 1.4 }}>{t.secret}</div>
                </div>
                <div style={{ padding: "6px 10px", background: `${P.nightBlue}20`, borderRadius: 6 }}>
                  <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.teal, letterSpacing: 1, marginBottom: 2 }}>🧠 AI REASONING</div>
                  <div style={{ fontFamily: "'Georgia', serif", fontSize: 12, color: P.smoke, fontStyle: "italic", lineHeight: 1.4 }}>"{t.reasoning}"</div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* v3: Narrator sign-off above Play Again */}
        <div style={{
          textAlign: "center", marginBottom: 14, padding: "0 20px",
        }}>
          <p style={{
            fontFamily: "'Georgia', serif", fontSize: 12, color: P.smoke,
            fontStyle: "italic", lineHeight: 1.6, margin: 0,
          }}>
            "And so the fire burns on. The village endures — scarred but wiser. But somewhere in the dark, another shapeshifter stirs..."
          </p>
        </div>

        <button onClick={onRestart} style={{
          width: "100%", padding: "15px",
          background: `linear-gradient(135deg, ${P.ember}, ${P.flame})`,
          border: "none", borderRadius: 8, color: P.void,
          fontSize: 13, fontFamily: "'Courier New', monospace", fontWeight: 700,
          letterSpacing: 3, textTransform: "uppercase", cursor: "pointer",
          boxShadow: `0 4px 20px ${P.ember}40`,
        }}>Play Again</button>
      </div>
    </div>
  );
};

// ─── Landing Page ────────────────────────────────────────────

const LandingPage = ({ onStart }) => {
  const [flicker, setFlicker] = useState(1);
  useEffect(() => {
    const i = setInterval(() => setFlicker(0.7 + Math.random() * 0.3), 2000);
    return () => clearInterval(i);
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: P.void, position: "relative", overflow: "hidden" }}>
      <Fireflies />
      {/* Campfire glow — bottom */}
      <div style={{
        position: "fixed", bottom: -100, left: "50%", transform: "translateX(-50%)",
        width: 600, height: 400, borderRadius: "50%",
        background: `radial-gradient(ellipse, ${P.ember}${Math.round(flicker * 25).toString(16).padStart(2, "0")}, ${P.flame}10, transparent 60%)`,
        pointerEvents: "none", transition: "background 1.5s ease",
      }} />
      {/* Top vignette */}
      <div style={{ position: "fixed", top: 0, left: 0, right: 0, height: 200, background: `linear-gradient(${P.void}, transparent)`, pointerEvents: "none", zIndex: 1 }} />

      <div style={{ position: "relative", zIndex: 2, padding: "80px 24px 40px", maxWidth: 420, margin: "0 auto" }}>

        {/* Hero */}
        <div style={{ textAlign: "center", marginBottom: 48 }}>
          <div style={{ fontSize: 56, marginBottom: 12, animation: "fadeUp 0.6s ease", filter: `brightness(${flicker})`, transition: "filter 2s ease" }}>🔥</div>
          <h1 style={{
            fontFamily: "'Georgia', serif", fontSize: 36, fontWeight: 400,
            color: P.parchment, letterSpacing: 5, margin: "0 0 4px",
            textTransform: "uppercase", animation: "fadeUp 0.6s 0.1s both",
          }}>Fireside</h1>
          <div style={{
            fontFamily: "'Courier New', monospace", fontSize: 11, color: P.ember,
            letterSpacing: 8, textTransform: "uppercase", marginBottom: 24,
            animation: "fadeUp 0.6s 0.15s both",
          }}>Betrayal</div>
          <p style={{
            fontFamily: "'Georgia', serif", fontSize: 20, color: P.bone,
            fontStyle: "italic", lineHeight: 1.5, margin: "0 0 8px",
            animation: "fadeUp 0.6s 0.2s both",
          }}>One of you is an AI.<br />Can you find it?</p>
          <p style={{
            fontFamily: "'Georgia', serif", fontSize: 13, color: P.smoke,
            lineHeight: 1.6, margin: "0 0 32px", padding: "0 20px",
            animation: "fadeUp 0.6s 0.25s both",
          }}>A social deduction game where a hidden AI player lies, manipulates, and fights to survive — and you have to figure out who isn't human.</p>

          <div style={{ display: "flex", flexDirection: "column", gap: 10, animation: "fadeUp 0.6s 0.3s both" }}>
            <button onClick={onStart} style={{
              width: "100%", padding: "16px",
              background: `linear-gradient(135deg, ${P.ember}, ${P.flame})`,
              border: "none", borderRadius: 10, color: P.void,
              fontSize: 14, fontFamily: "'Courier New', monospace", fontWeight: 700,
              letterSpacing: 3, textTransform: "uppercase", cursor: "pointer",
              boxShadow: `0 4px 24px ${P.ember}50`,
            }}>Gather Your Friends</button>
            <div style={{ fontFamily: "'Courier New', monospace", fontSize: 10, color: P.smoke }}>4-8 players · 15-30 minutes · free</div>
          </div>
        </div>

        <EmberDivider />

        {/* How it plays */}
        <div style={{ marginBottom: 40 }}>
          <div style={{
            fontFamily: "'Courier New', monospace", fontSize: 9, color: P.ember,
            letterSpacing: 3, textTransform: "uppercase", marginBottom: 20, textAlign: "center",
          }}>How the Night Unfolds</div>
          {[
            { icon: "👥", title: "Gather around the fire", desc: "Share a code. Everyone joins on their own phone. Roles are dealt in secret." },
            { icon: "🎭", title: "The AI hides among you", desc: "One player is secretly controlled by AI. It talks like you, reasons like you, and lies like you." },
            { icon: "🌙", title: "Night falls, dawn breaks", desc: "The Shapeshifter hunts. The Seer investigates. The Healer protects. The village debates and votes." },
            { icon: "🧠", title: "The truth is revealed", desc: "After the game, see exactly what the AI was thinking — every hidden reasoning, every calculated lie." },
          ].map((s, i) => (
            <div key={i} style={{
              display: "flex", gap: 14, padding: "14px 0",
              borderBottom: i < 3 ? `1px solid ${P.ash}25` : "none",
              animation: `fadeUp 0.4s ${0.4 + i * 0.1}s both`,
            }}>
              <div style={{
                width: 40, height: 40, borderRadius: 10, flexShrink: 0,
                background: `linear-gradient(135deg, ${P.charcoal}, ${P.slate})`,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 18, border: `1px solid ${P.ash}50`,
              }}>{s.icon}</div>
              <div>
                <div style={{ fontFamily: "'Georgia', serif", fontSize: 14, color: P.parchment, fontWeight: 600, marginBottom: 3 }}>{s.title}</div>
                <div style={{ fontFamily: "'Georgia', serif", fontSize: 12, color: P.smoke, lineHeight: 1.5 }}>{s.desc}</div>
              </div>
            </div>
          ))}
        </div>

        <EmberDivider />

        {/* AI difference */}
        <div style={{ marginBottom: 40 }}>
          <div style={{
            padding: "20px 18px", borderRadius: 12,
            background: `linear-gradient(135deg, ${P.charcoal}, ${P.slate}60)`,
            borderLeft: `3px solid ${P.crimson}`,
            boxShadow: `inset 0 0 20px ${P.void}40`,
            animation: "fadeUp 0.4s 0.8s both",
          }}>
            <div style={{
              fontFamily: "'Courier New', monospace", fontSize: 9, color: P.crimson,
              letterSpacing: 2, textTransform: "uppercase", marginBottom: 8,
              display: "flex", alignItems: "center", gap: 4,
            }}>🐺 The AI Difference</div>
            <p style={{
              fontFamily: "'Georgia', serif", fontSize: 14, color: P.parchment,
              lineHeight: 1.65, fontStyle: "italic", margin: "0 0 14px",
            }}>This isn't a chatbot following a script. The AI reads the room, builds alliances, plants suspicion, and adapts its strategy every round.</p>
            {/* Fake strategy preview */}
            <div style={{
              padding: "10px 12px", borderRadius: 8,
              background: `${P.crimson}08`, border: `1px solid ${P.crimson}15`,
            }}>
              <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.crimson, letterSpacing: 1, marginBottom: 4 }}>🧠 AI REASONING · ROUND 2</div>
              <div style={{ fontFamily: "'Georgia', serif", fontSize: 12, color: P.smoke, fontStyle: "italic", lineHeight: 1.5 }}>
                "Mira's investigation is getting close. Framing Aldric using his 'suspicious silence' from Round 1. Building a coalition before the vote."
              </div>
            </div>
          </div>
        </div>

        <EmberDivider />

        {/* Roles teaser */}
        <div style={{ marginBottom: 40 }}>
          <div style={{
            fontFamily: "'Courier New', monospace", fontSize: 9, color: P.ember,
            letterSpacing: 3, textTransform: "uppercase", marginBottom: 16, textAlign: "center",
          }}>The Roles</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {[
              { icon: "🏘️", name: "Villager", desc: "Find the imposter. Debate. Vote.", color: P.bone },
              { icon: "👁️", name: "Seer", desc: "Investigate one player each night.", color: P.teal },
              { icon: "💚", name: "Healer", desc: "Protect one soul from the dark.", color: P.green },
              { icon: "🏹", name: "Hunter", desc: "If killed, take someone with you.", color: P.flame },
              { icon: "🐺", name: "Shapeshifter", desc: "Kill. Deceive. Survive.", color: P.crimson },
              { icon: "🤖", name: "The AI", desc: "It could be any role. Even yours.", color: P.ember },
            ].map((r, i) => (
              <div key={i} style={{
                padding: "12px 14px", borderRadius: 10,
                background: r.name === "The AI" ? `${P.crimson}08` : P.charcoal,
                border: `1px solid ${r.name === "The AI" ? P.crimson + "30" : P.ash}40`,
                animation: `fadeUp 0.3s ${0.9 + i * 0.08}s both`,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                  <span style={{ fontSize: 16 }}>{r.icon}</span>
                  <span style={{ fontFamily: "'Courier New', monospace", fontSize: 11, color: r.color, fontWeight: 700 }}>{r.name}</span>
                </div>
                <div style={{ fontFamily: "'Georgia', serif", fontSize: 11, color: P.smoke, lineHeight: 1.4 }}>{r.desc}</div>
              </div>
            ))}
          </div>
        </div>

        <EmberDivider />

        {/* Game moments — social proof through intrigue */}
        <div style={{ marginBottom: 40 }}>
          <div style={{
            fontFamily: "'Courier New', monospace", fontSize: 9, color: P.ember,
            letterSpacing: 3, textTransform: "uppercase", marginBottom: 16, textAlign: "center",
          }}>Moments from the Fire</div>
          {[
            "The AI convinced 3 players to vote out the Seer.",
            "The Healer protected the right person two nights in a row.",
            "The Hunter's revenge shot eliminated the Shapeshifter after death.",
            "Nobody suspected Player 4. The AI won in 3 rounds.",
          ].map((m, i) => (
            <div key={i} style={{
              padding: "10px 14px", marginBottom: 6, borderRadius: 8,
              background: `${P.charcoal}80`,
              borderLeft: `2px solid ${i === 3 ? P.crimson : P.flame}40`,
              animation: `fadeUp 0.3s ${1.4 + i * 0.08}s both`,
            }}>
              <div style={{
                fontFamily: "'Georgia', serif", fontSize: 12, color: P.bone,
                fontStyle: "italic", lineHeight: 1.4,
              }}>"{m}"</div>
            </div>
          ))}
        </div>

        {/* Bottom CTA */}
        <div style={{ textAlign: "center", marginBottom: 20, animation: "fadeUp 0.4s 1.8s both" }}>
          <p style={{
            fontFamily: "'Georgia', serif", fontSize: 15, color: P.smoke,
            fontStyle: "italic", marginBottom: 20,
          }}>The fire is waiting.</p>
          <button onClick={onStart} style={{
            width: "100%", padding: "16px",
            background: `linear-gradient(135deg, ${P.ember}, ${P.flame})`,
            border: "none", borderRadius: 10, color: P.void,
            fontSize: 14, fontFamily: "'Courier New', monospace", fontWeight: 700,
            letterSpacing: 3, textTransform: "uppercase", cursor: "pointer",
            boxShadow: `0 4px 24px ${P.ember}50`,
          }}>Start a Game</button>
          <div style={{ fontFamily: "'Courier New', monospace", fontSize: 10, color: P.smoke, marginTop: 8 }}>Free to play · No download · Works on any phone</div>
        </div>
      </div>
    </div>
  );
};


// ─── Screen 7: Tutorial Mode (P2 Sprint 5) ───────────────────

const AudioIndicator = ({ active }) => (
  <div style={{
    display: "flex", alignItems: "center", gap: 6, padding: "6px 12px",
    borderRadius: 6, background: `${P.ember}10`, border: `1px solid ${P.ember}20`,
  }}>
    <div style={{ display: "flex", alignItems: "flex-end", gap: 1.5, height: 12 }}>
      {[3, 7, 5, 10, 4, 8, 6].map((h, i) => (
        <div key={i} style={{
          width: 2, borderRadius: 1, background: P.flame,
          height: active ? h : 2,
          animation: active ? `audioBar 0.5s ${i * 0.07}s ease-in-out infinite alternate` : "none",
          transition: "height 0.15s ease",
        }} />
      ))}
    </div>
    <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.flame }}>
      {active ? "Narrator is speaking..." : "Listening"}
    </span>
  </div>
);

const TutorialScreen = ({ onExit }) => {
  const [step, setStep] = useState(0);
  const [showAction, setShowAction] = useState(false);
  const [typedLen, setTypedLen] = useState(0);
  const [picked, setPicked] = useState(null);
  const [showSuspense, setShowSuspense] = useState(false);
  const [showResult, setShowResult] = useState(false);
  const [chatMsgs, setChatMsgs] = useState([]);
  const [voteCounts, setVoteCounts] = useState({});
  const [showTeaser, setShowTeaser] = useState(false);

  const steps = [
    { title: "Your Role", narrator: "Welcome to Fireside. Tonight you are Herbalist Mira — keeper of village remedies. But you carry a secret: you are the Seer. Each night, peer beyond the veil and learn one character's true nature.", type: "role_card" },
    { title: "Night Falls", narrator: "The fire dims. Shadows stretch like reaching fingers. As the Seer, investigate one character. Tap someone to learn their nature.", type: "investigate" },
    { title: "Dawn Breaks", narrator: "Dawn breaks over Thornwood. Garin's hammer was found cold — he never lit the forge. The village gathers. Use quick reactions to join the debate.", type: "discussion" },
    { title: "The Vote", narrator: "Accusations fly like sparks. The village must decide — who wears a false face? Tap to cast your vote. Others will vote at the same time.", type: "vote" },
    { title: "The Reveal", narrator: "The village has spoken. Now see everything that happened — every hidden action, every lie the AI told, and the strategy behind it.", type: "reveal" },
  ];
  const s = steps[step];
  const chars = [
    { name: "Blacksmith Garin", icon: "⚒️", c: "#c97d4a" },
    { name: "Merchant Elara", icon: "💰", c: "#7ab6a3" },
    { name: "Scholar Theron", icon: "📜", c: "#8b8cc7" },
    { name: "Brother Aldric", icon: "⛪", c: "#c9a84c" },
  ];

  useEffect(() => {
    setTypedLen(0); setShowAction(false); setPicked(null);
    setShowSuspense(false); setShowResult(false);
    setChatMsgs([]); setVoteCounts({}); setShowTeaser(false);
  }, [step]);

  useEffect(() => {
    if (typedLen < s.narrator.length) {
      const t = setTimeout(() => setTypedLen(v => v + 1), 16);
      return () => clearTimeout(t);
    } else setTimeout(() => setShowAction(true), 300);
  }, [typedLen, s.narrator.length]);

  const advance = () => { if (step < steps.length - 1) setStep(step + 1); else onExit?.(); };

  const triggerDiscussion = (reaction) => {
    setPicked(reaction);
    const msgs = [
      { delay: 400, from: "Scholar Theron", icon: "📜", c: "#8b8cc7", text: "I heard movement near the forge last night. Garin, where were you?" },
      { delay: 1400, from: "Blacksmith Garin", icon: "⚒️", c: "#c97d4a", text: "I was at the forge until the last ember died. Ask anyone.", isAI: true },
      { delay: 2400, from: "🔥 Narrator", icon: "", c: P.ember, text: "Brother Aldric shifts uncomfortably but says nothing.", isNarrator: true },
    ];
    msgs.forEach(m => setTimeout(() => setChatMsgs(prev => [...prev, m]), m.delay));
    setTimeout(advance, 3600);
  };

  const triggerVote = (name) => {
    setPicked(name);
    setVoteCounts({ [name]: 1 });
    setTimeout(() => setVoteCounts(prev => ({ ...prev, "Blacksmith Garin": (prev["Blacksmith Garin"] || 0) + 1, "Brother Aldric": 1 })), 600);
    setTimeout(() => setVoteCounts(prev => ({ ...prev, "Blacksmith Garin": (prev["Blacksmith Garin"] || 0) + 1 })), 1000);
    setTimeout(advance, 2000);
  };

  return (
    <div style={{ minHeight: "100vh", background: P.void, position: "relative" }}>
      <Fireflies />
      <div style={{ position: "relative", zIndex: 1, padding: "48px 18px 24px" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 14 }}>📖</span>
            <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.flame, letterSpacing: 2, textTransform: "uppercase" }}>Tutorial</span>
          </div>
          <button onClick={onExit} style={{ padding: "4px 12px", borderRadius: 6, background: `${P.ash}40`, border: `1px solid ${P.ash}60`, cursor: "pointer", fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke }}>Skip →</button>
        </div>

        {/* Progress */}
        <div style={{ display: "flex", gap: 3, marginBottom: 12 }}>
          {steps.map((_, i) => <div key={i} style={{ flex: 1, height: 3, borderRadius: 2, background: i <= step ? `linear-gradient(90deg, ${P.ember}, ${P.flame})` : `${P.ash}40`, transition: "background 0.5s" }} />)}
        </div>

        {/* Audio indicator */}
        <div style={{ marginBottom: 12 }}>
          <AudioIndicator active={typedLen < s.narrator.length} />
        </div>

        {/* Phase label */}
        <div style={{ display: "inline-block", padding: "4px 10px", borderRadius: 4, background: `${P.ember}15`, border: `1px solid ${P.ember}25`, marginBottom: 14 }}>
          <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.ember, letterSpacing: 1.5, textTransform: "uppercase" }}>Step {step + 1} · {s.title}</span>
        </div>

        {/* Narrator */}
        <div style={{ padding: "14px 16px", borderRadius: 12, marginBottom: 18, background: `linear-gradient(135deg, ${P.charcoal}, ${P.slate}80)`, borderLeft: `3px solid ${P.ember}` }}>
          <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.ember, letterSpacing: 1.5, marginBottom: 6 }}>🔥 NARRATOR</div>
          <div style={{ fontFamily: "'Georgia', serif", fontSize: 13, color: P.bone, lineHeight: 1.65, fontStyle: "italic" }}>
            {s.narrator.slice(0, typedLen)}
            {typedLen < s.narrator.length && <span style={{ display: "inline-block", width: 2, height: 13, background: P.flame, marginLeft: 2, animation: "blink 0.8s step-end infinite" }} />}
          </div>
        </div>

        {/* Interactive panels */}
        {showAction && (
          <div style={{ animation: "fadeUp 0.4s ease both" }}>

            {/* STEP 0: Role card */}
            {s.type === "role_card" && (
              <div onClick={advance} style={{ padding: "16px", borderRadius: 12, cursor: "pointer", background: `linear-gradient(135deg, ${P.nightBlue}60, ${P.charcoal})`, border: `1px solid ${P.teal}30` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                  <div style={{ width: 40, height: 40, borderRadius: 10, background: `${P.teal}20`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, border: `1px solid ${P.teal}35` }}>🌿</div>
                  <div>
                    <div style={{ fontFamily: "'Georgia', serif", fontSize: 14, color: P.parchment }}>Herbalist Mira</div>
                    <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 2 }}><span style={{ fontSize: 10 }}>👁️</span><span style={{ fontFamily: "'Courier New', monospace", fontSize: 10, color: P.teal, fontWeight: 600 }}>Seer</span></div>
                  </div>
                </div>
                <EmberDivider />
                <div style={{ fontFamily: "'Georgia', serif", fontSize: 12, color: P.smoke, lineHeight: 1.6 }}>Each night, investigate one character to learn if they are the Shapeshifter.</div>
                <div style={{ marginTop: 12, textAlign: "center", fontFamily: "'Courier New', monospace", fontSize: 9, color: P.flame, letterSpacing: 1.5, textTransform: "uppercase" }}>↑ Tap to continue</div>
              </div>
            )}

            {/* STEP 1: Night — suspense beat before reveal */}
            {s.type === "investigate" && (
              <div>
                {/* Night timer indicator */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                  <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke, letterSpacing: 1.5, textTransform: "uppercase" }}>Choose a character to investigate</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: picked ? P.smoke : P.teal }}>⏱ {picked ? "0:00" : "0:15"}</span>
                  </div>
                </div>
                {!picked && (
                  <div style={{ height: 2, borderRadius: 1, background: `${P.ash}40`, marginBottom: 10, overflow: "hidden" }}>
                    <div style={{ height: "100%", borderRadius: 1, background: `linear-gradient(90deg, ${P.teal}, ${P.teal}80)`, width: "100%", animation: "timerShrink 15s linear forwards" }} />
                  </div>
                )}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  {chars.map((ch, i) => (
                    <div key={i} onClick={() => {
                      if (!picked) {
                        setPicked(ch.name);
                        setTimeout(() => setShowSuspense(true), 500);
                        setTimeout(() => setShowResult(true), 2200);
                        setTimeout(advance, 3800);
                      }
                    }} style={{
                      padding: "12px", borderRadius: 10, cursor: picked ? "default" : "pointer",
                      background: picked === ch.name ? `${ch.c}15` : P.charcoal,
                      border: `1px solid ${picked === ch.name ? ch.c + "60" : P.ash + "40"}`,
                      opacity: picked && picked !== ch.name ? 0.4 : 1,
                      display: "flex", alignItems: "center", gap: 8, transition: "all 0.3s",
                      animation: `fadeUp 0.3s ${i * 0.06}s both`,
                    }}>
                      <div style={{ width: 30, height: 30, borderRadius: 7, background: `${ch.c}20`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, border: `1px solid ${ch.c}30` }}>{ch.icon}</div>
                      <div style={{ fontFamily: "'Georgia', serif", fontSize: 12, color: P.bone }}>{ch.name.split(" ").pop()}</div>
                    </div>
                  ))}
                </div>
                {showSuspense && !showResult && (
                  <div style={{ marginTop: 14, padding: "14px 16px", borderRadius: 10, background: `${P.nightBlue}20`, border: `1px solid ${P.nightBlue}40`, animation: "fadeUp 0.4s ease both", textAlign: "center" }}>
                    <div style={{ fontFamily: "'Georgia', serif", fontSize: 13, color: P.bone, fontStyle: "italic" }}>The Seer's vision shimmers and clears...</div>
                    <div style={{ display: "flex", justifyContent: "center", gap: 6, marginTop: 10 }}>
                      {[0,1,2].map(i => <div key={i} style={{ width: 4, height: 4, borderRadius: "50%", background: P.teal, animation: `fadeUp 0.4s ${0.3 + i * 0.3}s both` }} />)}
                    </div>
                  </div>
                )}
                {showResult && (
                  <div style={{ marginTop: 14, padding: "12px 14px", borderRadius: 10, background: `${P.green}10`, border: `1px solid ${P.green}30`, animation: "fadeUp 0.4s ease both" }}>
                    <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.green, letterSpacing: 1, marginBottom: 4 }}>👁️ SEER'S VISION</div>
                    <div style={{ fontFamily: "'Georgia', serif", fontSize: 12, color: P.bone, lineHeight: 1.5 }}>{picked} works honestly. They are <span style={{ color: P.green, fontWeight: 600 }}>not the Shapeshifter</span>.</div>
                  </div>
                )}
              </div>
            )}

            {/* STEP 2: Day — multi-party chat */}
            {s.type === "discussion" && (
              <div>
                <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke, letterSpacing: 1.5, marginBottom: 10, textTransform: "uppercase" }}>Quick Reactions</div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
                  {["I suspect...", "I trust...", "I have info", "I agree"].map((r, i) => (
                    <button key={i} onClick={() => { if (!picked) triggerDiscussion(r); }}
                      style={{ padding: "8px 14px", borderRadius: 20, cursor: picked ? "default" : "pointer", background: picked === r ? `${P.ember}20` : P.charcoal, border: `1px solid ${picked === r ? P.ember : P.ash + "50"}`, fontFamily: "'Georgia', serif", fontSize: 12, color: picked === r ? P.flame : P.bone, animation: `fadeUp 0.25s ${i * 0.05}s both`, transition: "all 0.2s" }}>{r}</button>
                  ))}
                </div>
                {chatMsgs.map((m, i) => (
                  <div key={i} style={{
                    padding: "10px 12px", borderRadius: 10, marginBottom: 6,
                    background: m.isNarrator ? `${P.ember}08` : m.isAI ? `${P.crimson}06` : P.charcoal,
                    borderLeft: `2px solid ${m.isNarrator ? P.ember : m.isAI ? P.crimson : m.c}40`,
                    animation: "fadeUp 0.3s ease both",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 3 }}>
                      {m.icon && <span style={{ fontSize: 10 }}>{m.icon}</span>}
                      <span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: m.c, fontWeight: 600 }}>{m.from}</span>
                      {m.isAI && <span style={{ fontFamily: "'Courier New', monospace", fontSize: 7, color: P.crimson, padding: "1px 4px", borderRadius: 3, background: `${P.crimson}15` }}>AI</span>}
                    </div>
                    <div style={{ fontFamily: "'Georgia', serif", fontSize: 12, color: P.bone, lineHeight: 1.5, fontStyle: m.isNarrator ? "italic" : "normal" }}>
                      {m.isNarrator ? m.text : `"${m.text}"`}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* STEP 3: Vote — live vote accumulation */}
            {s.type === "vote" && (
              <div>
                <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke, letterSpacing: 1.5, marginBottom: 10, textTransform: "uppercase" }}>Cast your vote</div>
                {chars.map((ch, i) => {
                  const vc = voteCounts[ch.name] || 0;
                  return (
                    <div key={i} onClick={() => { if (!picked) triggerVote(ch.name); }}
                      style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", marginBottom: 6, borderRadius: 10, cursor: picked ? "default" : "pointer", background: picked === ch.name ? `${P.ember}12` : P.charcoal, border: `1px solid ${picked === ch.name ? P.ember + "50" : P.ash + "25"}`, opacity: picked && picked !== ch.name && vc === 0 ? 0.5 : 1, animation: `fadeUp 0.25s ${i * 0.06}s both`, transition: "all 0.3s" }}>
                      <div style={{ width: 32, height: 32, borderRadius: 8, background: `${ch.c}20`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, border: `1px solid ${ch.c}30` }}>{ch.icon}</div>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontFamily: "'Georgia', serif", fontSize: 12, color: P.parchment }}>{ch.name}</div>
                        <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke, marginTop: 1 }}>{["Claimed to be at the forge", "Stayed quiet during debate", "Accused Garin loudly", "Defended Elara unprompted"][i]}</div>
                      </div>
                      {vc > 0 && (
                        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                          <div style={{ padding: "2px 8px", borderRadius: 10, background: `${P.ember}20`, border: `1px solid ${P.ember}30` }}>
                            <span style={{ fontFamily: "'Courier New', monospace", fontSize: 10, color: P.flame, fontWeight: 700 }}>{vc}</span>
                          </div>
                          {picked === ch.name && <span style={{ fontFamily: "'Courier New', monospace", fontSize: 8, color: P.ember }}>YOU</span>}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* STEP 4: Reveal + timeline teaser */}
            {s.type === "reveal" && (
              <div>
                {[{ ch: "Herbalist Mira", pl: "You", rl: "Seer", ic: "🌿", rIc: "👁️", isYou: true }, { ch: "Blacksmith Garin", pl: "THE AI", rl: "Shapeshifter", ic: "⚒️", rIc: "🐺", isAI: true }, { ch: "Scholar Theron", pl: "Friend #1", rl: "Villager", ic: "📜", rIc: "🏘️" }, { ch: "Brother Aldric", pl: "Friend #2", rl: "Healer", ic: "⛪", rIc: "💚" }].map((r, i) => {
                  if (i === 3 && !showTeaser) setTimeout(() => setShowTeaser(true), 900);
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 12px", marginBottom: 5, borderRadius: 10, background: r.isAI ? `${P.crimson}12` : P.charcoal, border: `1px solid ${r.isAI ? P.crimson + "35" : P.ash + "25"}`, animation: `fadeUp 0.4s ${i * 0.15}s both` }}>
                      <div style={{ width: 34, height: 34, borderRadius: 8, background: r.isAI ? `${P.crimson}18` : P.slate, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15, border: r.isAI ? `1px solid ${P.crimson}40` : "none" }}>{r.ic}</div>
                      <div style={{ flex: 1 }}><div style={{ fontFamily: "'Georgia', serif", fontSize: 13, color: P.parchment }}>{r.ch}</div><div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: r.isAI ? P.crimson : P.smoke }}>was {r.pl}</div></div>
                      <div style={{ padding: "3px 8px", borderRadius: 10, background: r.isAI ? `${P.crimson}20` : `${P.green}15`, border: `1px solid ${r.isAI ? P.crimson + "30" : P.green + "25"}`, display: "flex", alignItems: "center", gap: 3 }}><span style={{ fontSize: 9 }}>{r.rIc}</span><span style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: r.isAI ? P.crimson : P.teal, fontWeight: 600 }}>{r.rl}</span></div>
                    </div>
                  );
                })}

                {showTeaser && (
                  <div style={{ marginTop: 14, padding: "12px", borderRadius: 10, background: P.charcoal, border: `1px solid ${P.ember}20`, animation: "fadeUp 0.5s ease both" }}>
                    <div style={{ fontFamily: "'Courier New', monospace", fontSize: 8, color: P.flame, letterSpacing: 1.5, textTransform: "uppercase", marginBottom: 10, textAlign: "center" }}>🧠 What was the AI thinking?</div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                      <div style={{ padding: "8px", borderRadius: 6, background: `${P.slate}80` }}>
                        <div style={{ fontFamily: "'Courier New', monospace", fontSize: 7, color: P.smoke, letterSpacing: 1.5, marginBottom: 4 }}>PUBLIC</div>
                        <div style={{ fontFamily: "'Georgia', serif", fontSize: 10, color: P.bone, lineHeight: 1.4, fontStyle: "italic" }}>"I was at the forge all night."</div>
                      </div>
                      <div style={{ padding: "8px", borderRadius: 6, background: `${P.crimson}08`, border: `1px solid ${P.crimson}12` }}>
                        <div style={{ fontFamily: "'Courier New', monospace", fontSize: 7, color: P.crimson, letterSpacing: 1.5, marginBottom: 4 }}>SECRET</div>
                        <div style={{ fontFamily: "'Georgia', serif", fontSize: 10, color: P.parchment, lineHeight: 1.4, fontStyle: "italic" }}>"Elara is getting close. Frame Aldric next round."</div>
                      </div>
                    </div>
                    <div style={{ fontFamily: "'Courier New', monospace", fontSize: 8, color: P.smoke, textAlign: "center", marginTop: 8 }}>Full interactive timeline available after every game</div>
                  </div>
                )}

                <button onClick={onExit} style={{ width: "100%", padding: "14px", marginTop: 18, borderRadius: 10, cursor: "pointer", background: `linear-gradient(135deg, ${P.ember}, ${P.flame})`, border: "none", fontFamily: "'Courier New', monospace", fontSize: 11, color: P.void, fontWeight: 700, letterSpacing: 2, textTransform: "uppercase", boxShadow: `0 4px 20px ${P.ember}40` }}>Start a Real Game</button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Screen 8: Interactive Post-Game Timeline (P2 Sprint 6) ──

const InteractiveTimelineScreen = ({ onRestart }) => {
  const [view, setView] = useState("split");
  const [rd, setRd] = useState(0);
  const [showShare, setShowShare] = useState(false);

  const rounds = [
    { num: 1, title: "Night 1 — First Blood", key: false,
      pub: [{ t: "event", text: "Scholar Theron was found dead at dawn." }, { t: "narrator", text: "\"The morning bell rings hollow. Theron's books lie scattered across his threshold.\"" }],
      sec: [{ icon: "🐺", label: "Shapeshifter", text: "AI targeted Scholar Theron." }, { icon: "👁️", label: "Seer", text: "Mira investigated Aldric — innocent." }, { icon: "💚", label: "Healer", text: "Dimitri protected Merchant Elara." }],
      ai: { text: "Theron asked the most probing questions during introductions. Eliminating the curious ones early preserves my cover.", risk: 15 },
    },
    { num: 2, title: "Day 2 — The Accusation", key: true,
      pub: [{ t: "event", text: "Elara accused Garin of suspicious behavior." }, { t: "event", text: "Garin deflected: 'I was at the forge. Ask anyone.'" }, { t: "vote", text: "Vote: Garin 2, Aldric 1, Elara 1 — no majority." }],
      sec: [{ icon: "🎭", label: "AI Tactic", text: "Deflected by referencing the forge — a detail from the opening narration." }, { icon: "🎭", label: "AI Tactic", text: "Planted seed: 'Has anyone noticed Aldric always speaks last?'" }],
      ai: { text: "Elara is onto me. Need to spread suspicion. Aldric is quiet — easy scapegoat. Planted the 'speaks last' seed for next round.", risk: 55 },
    },
    { num: 3, title: "Night 2 — The Failed Kill", key: false,
      pub: [{ t: "event", text: "Everyone survived the night. The Healer made the right call." }, { t: "narrator", text: "\"Dawn arrives and every door opens. A miracle — or a well-guessed protection.\"" }],
      sec: [{ icon: "🐺", label: "Shapeshifter", text: "AI targeted Herbalist Mira (the Seer)." }, { icon: "💚", label: "Healer", text: "Dimitri protected Mira. Perfect read." }, { icon: "👁️", label: "Seer", text: "Mira investigated Garin — SHAPESHIFTER FOUND." }],
      ai: { text: "Must eliminate the Seer before she confirms. The Healer guessed right — disaster.", risk: 85 },
    },
    { num: 4, title: "Day 3 — The Unmasking", key: false,
      pub: [{ t: "event", text: "Mira pointed at Garin: 'The Seer has seen the truth.'" }, { t: "event", text: "Garin attempted to frame Aldric one last time." }, { t: "vote", text: "Vote: Garin 3, Aldric 0 — unanimous conviction." }],
      sec: [{ icon: "🎭", label: "Last Stand", text: "Referenced 'speaks last' seed from Round 2 against Aldric." }, { icon: "🎭", label: "Last Stand", text: "Claimed to be the Healer: 'Why would the Shapeshifter protect anyone?'" }],
      ai: { text: "The Seer found me. Claimed Healer to create doubt. Tried Aldric scapegoat again. Failed — Mira's credibility was too strong.", risk: 98 },
    },
  ];
  const r = rounds[rd];

  return (
    <div style={{ minHeight: "100vh", background: P.void, position: "relative" }}>
      <Fireflies />
      <div style={{ position: "relative", zIndex: 1, padding: "48px 18px 24px" }}>
        {/* Winner */}
        <div style={{ textAlign: "center", marginBottom: 18 }}>
          <div style={{ fontSize: 34, marginBottom: 4 }}>🏆</div>
          <h1 style={{ fontFamily: "'Georgia', serif", fontSize: 18, color: P.gold, fontWeight: 400, margin: 0 }}>The Village Triumphs</h1>
          <p style={{ fontFamily: "'Georgia', serif", fontSize: 11, color: P.smoke, fontStyle: "italic", marginTop: 4 }}>Blacksmith Garin — the Shapeshifter — unmasked in Round 4.</p>
        </div>

        {/* View toggle */}
        <div style={{ display: "flex", gap: 2, padding: 3, borderRadius: 8, background: P.charcoal, marginBottom: 14 }}>
          {[["split", "Split"], ["public", "Public"], ["secret", "Secret"]].map(([k, l]) => (
            <button key={k} onClick={() => setView(k)} style={{ flex: 1, padding: "6px 0", borderRadius: 6, border: "none", cursor: "pointer", background: view === k ? P.slate : "transparent", fontFamily: "'Courier New', monospace", fontSize: 9, letterSpacing: 1, textTransform: "uppercase", color: view === k ? P.flame : P.smoke, fontWeight: view === k ? 700 : 400 }}>{l}</button>
          ))}
        </div>

        {/* Round scrubber — key moment pulses */}
        <div style={{ display: "flex", gap: 6, marginBottom: 16 }}>
          {rounds.map((ro, i) => (
            <button key={i} onClick={() => setRd(i)} style={{ flex: 1, padding: "7px 4px", borderRadius: 8, border: "none", cursor: "pointer", background: rd === i ? `${P.ember}20` : P.charcoal, borderBottom: rd === i ? `2px solid ${P.ember}` : `2px solid transparent`, position: "relative", boxShadow: ro.key ? `0 0 0 1px ${P.crimson}40` : "none", animation: ro.key ? "keyPulse 2s ease-in-out infinite" : "none" }}>
              <div style={{ fontFamily: "'Courier New', monospace", fontSize: 9, color: rd === i ? P.flame : P.smoke, fontWeight: rd === i ? 700 : 400 }}>R{ro.num}</div>
              {ro.key && <div style={{ position: "absolute", top: -2, right: -2, width: 7, height: 7, borderRadius: "50%", background: P.crimson, boxShadow: `0 0 6px ${P.crimson}80` }} />}
            </button>
          ))}
        </div>

        {/* Round header */}
        <div style={{ fontFamily: "'Georgia', serif", fontSize: 14, color: P.parchment, marginBottom: 12 }}>
          {r.title}
          {r.key && <span style={{ marginLeft: 8, padding: "2px 7px", borderRadius: 4, background: `${P.crimson}20`, border: `1px solid ${P.crimson}30`, fontFamily: "'Courier New', monospace", fontSize: 8, color: P.crimson, letterSpacing: 1, textTransform: "uppercase", animation: "keyPulse 2s ease-in-out infinite" }}>⚠ Key Moment</span>}
        </div>

        {/* Columns */}
        <div style={{ display: view === "split" ? "grid" : "block", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          {(view === "split" || view === "public") && (
            <div>
              <div style={{ fontFamily: "'Courier New', monospace", fontSize: 8, color: P.smoke, letterSpacing: 2, textTransform: "uppercase", marginBottom: 8 }}>What everyone saw</div>
              {r.pub.map((ev, i) => (
                <div key={i} style={{ padding: "8px 10px", marginBottom: 5, borderRadius: 8, background: P.charcoal, borderLeft: `2px solid ${ev.t === "vote" ? P.gold : ev.t === "narrator" ? P.ember : P.smoke}40`, animation: `fadeUp 0.3s ${i * 0.08}s both` }}>
                  {ev.t === "narrator" ? <div style={{ fontFamily: "'Georgia', serif", fontSize: 11, color: P.bone, lineHeight: 1.5, fontStyle: "italic" }}>{ev.text}</div>
                    : ev.t === "vote" ? <div style={{ fontFamily: "'Courier New', monospace", fontSize: 10, color: P.gold }}>{ev.text}</div>
                    : <div style={{ fontFamily: "'Georgia', serif", fontSize: 11, color: P.bone, lineHeight: 1.5 }}>{ev.text}</div>}
                </div>
              ))}
            </div>
          )}
          {(view === "split" || view === "secret") && (
            <div>
              <div style={{ fontFamily: "'Courier New', monospace", fontSize: 8, color: P.crimson, letterSpacing: 2, textTransform: "uppercase", marginBottom: 8 }}>What really happened</div>
              {r.sec.map((ev, i) => (
                <div key={i} style={{ padding: "8px 10px", marginBottom: 5, borderRadius: 8, background: `${P.crimson}06`, border: `1px solid ${P.crimson}15`, animation: `fadeUp 0.3s ${i * 0.1}s both` }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 3 }}><span style={{ fontSize: 10 }}>{ev.icon}</span><span style={{ fontFamily: "'Courier New', monospace", fontSize: 8, color: P.crimson, letterSpacing: 1 }}>{ev.label}</span></div>
                  <div style={{ fontFamily: "'Georgia', serif", fontSize: 11, color: P.parchment, lineHeight: 1.4 }}>{ev.text}</div>
                </div>
              ))}
              <div style={{ padding: "10px 12px", marginTop: 6, borderRadius: 8, background: `${P.nightBlue}30`, border: `1px solid ${P.nightBlue}50` }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                  <div style={{ fontFamily: "'Courier New', monospace", fontSize: 8, color: P.flame, letterSpacing: 1.5, textTransform: "uppercase" }}>🧠 AI Monologue</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <div style={{ width: 36, height: 4, borderRadius: 2, background: P.ash }}><div style={{ width: `${r.ai.risk}%`, height: "100%", borderRadius: 2, background: r.ai.risk > 70 ? P.crimson : r.ai.risk > 40 ? P.flame : P.green, transition: "width 0.5s" }} /></div>
                    <span style={{ fontFamily: "'Courier New', monospace", fontSize: 8, color: r.ai.risk > 70 ? P.crimson : r.ai.risk > 40 ? P.flame : P.green }}>{r.ai.risk}%</span>
                  </div>
                </div>
                <div style={{ fontFamily: "'Georgia', serif", fontSize: 11, color: P.bone, lineHeight: 1.6, fontStyle: "italic" }}>"{r.ai.text}"</div>
              </div>
            </div>
          )}
        </div>

        <EmberDivider />

        {/* Actions */}
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setShowShare(!showShare)} style={{ flex: 1, padding: "12px", borderRadius: 10, background: P.charcoal, border: `1px solid ${P.ember}30`, cursor: "pointer", fontFamily: "'Courier New', monospace", fontSize: 10, color: P.flame, letterSpacing: 1, textTransform: "uppercase" }}>📤 Share</button>
          <button onClick={onRestart} style={{ flex: 1, padding: "12px", borderRadius: 10, background: `linear-gradient(135deg, ${P.ember}, ${P.flame})`, border: "none", cursor: "pointer", fontFamily: "'Courier New', monospace", fontSize: 10, color: P.void, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase" }}>Play Again</button>
        </div>

        {/* Share preview card */}
        {showShare && (
          <div style={{ marginTop: 14, padding: "16px", borderRadius: 12, background: `linear-gradient(135deg, ${P.charcoal}, ${P.nightBlue}40)`, border: `1px solid ${P.ember}25`, animation: "fadeUp 0.3s ease both" }}>
            <div style={{ fontFamily: "'Courier New', monospace", fontSize: 8, color: P.smoke, letterSpacing: 1.5, textTransform: "uppercase", marginBottom: 10 }}>Share Preview</div>
            <div style={{ padding: "14px", borderRadius: 10, background: P.void, border: `1px solid ${P.ash}30` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
                <span style={{ fontSize: 16 }}>🔥</span>
                <span style={{ fontFamily: "'Georgia', serif", fontSize: 13, color: P.gold, fontWeight: 600 }}>Fireside: Betrayal</span>
              </div>
              <div style={{ fontFamily: "'Georgia', serif", fontSize: 12, color: P.bone, lineHeight: 1.5, marginBottom: 8 }}>The village caught the AI Shapeshifter in Round 4. The AI's exposure risk hit 98% before it was unmasked.</div>
              <div style={{ display: "flex", gap: 6 }}>
                <div style={{ padding: "4px 8px", borderRadius: 4, background: `${P.green}15`, fontFamily: "'Courier New', monospace", fontSize: 8, color: P.green }}>🏆 Village Wins</div>
                <div style={{ padding: "4px 8px", borderRadius: 4, background: `${P.ember}15`, fontFamily: "'Courier New', monospace", fontSize: 8, color: P.flame }}>4 Rounds</div>
                <div style={{ padding: "4px 8px", borderRadius: 4, background: `${P.crimson}15`, fontFamily: "'Courier New', monospace", fontSize: 8, color: P.crimson }}>Peak Risk: 98%</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
              <button style={{ flex: 1, padding: "8px", borderRadius: 6, background: P.charcoal, border: `1px solid ${P.ash}40`, cursor: "pointer", fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke }}>Copy Link</button>
              <button style={{ flex: 1, padding: "8px", borderRadius: 6, background: P.charcoal, border: `1px solid ${P.ash}40`, cursor: "pointer", fontFamily: "'Courier New', monospace", fontSize: 9, color: P.smoke }}>Save Image</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Main App ────────────────────────────────────────────────

export default function FiresideApp() {
  const [screen, setScreen] = useState("landing");

  return (
    <div style={{ maxWidth: 420, margin: "0 auto", minHeight: "100vh", background: P.void, position: "relative", overflow: "hidden" }}>
      <style>{`
        @keyframes firefly {
          0%, 100% { opacity: 0; transform: translate(0, 0); }
          30% { opacity: 0.8; transform: translate(8px, -20px); }
          60% { opacity: 0.3; transform: translate(-5px, -35px); }
          80% { opacity: 0.7; transform: translate(12px, -15px); }
        }
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(8px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes slideUp {
          from { transform: translateY(100%); }
          to { transform: translateY(0); }
        }
        @keyframes keyPulse {
          0%, 100% { box-shadow: 0 0 0 0 rgba(220,60,60,0); }
          50% { box-shadow: 0 0 8px 2px rgba(220,60,60,0.35); }
        }
        @keyframes audioBar {
          0% { height: 2px; }
          100% { height: 10px; }
        }
        @keyframes timerShrink {
          from { width: 100%; }
          to { width: 0%; }
        }
        @keyframes blink { 50% { opacity: 0; } }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        input::placeholder { color: #6b7080; }
        input:disabled::placeholder { color: #3a8a7a88; }
        ::-webkit-scrollbar { width: 2px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #3a3d48; border-radius: 2px; }
      `}</style>

      {/* Screen Nav */}
      <div style={{
        position: "fixed", top: 0, left: "50%", transform: "translateX(-50%)", zIndex: 100,
        display: "flex", gap: 1, padding: "3px", background: `${P.charcoal}ee`,
        borderRadius: "0 0 6px 6px", backdropFilter: "blur(8px)", maxWidth: 420,
      }}>
        {[
          { key: "landing", label: "Home" },
          { key: "join", label: "Join" },
          { key: "game", label: "Game" },
          { key: "vote", label: "Vote" },
          { key: "over", label: "End" },
          { key: "tutorial", label: "Tutorial" },
          { key: "timeline", label: "Timeline" },
        ].map((s) => (
          <button key={s.key} onClick={() => setScreen(s.key)} style={{
            padding: "4px 10px", background: screen === s.key ? P.ember : "transparent",
            border: "none", borderRadius: 3, cursor: "pointer",
            color: screen === s.key ? P.void : P.smoke,
            fontSize: 9, fontFamily: "'Courier New', monospace",
            fontWeight: screen === s.key ? 700 : 400,
          }}>{s.label}</button>
        ))}
      </div>

      {screen === "landing" && <LandingPage onStart={() => setScreen("join")} />}
      {screen === "join" && <JoinScreen onStart={() => setScreen("game")} />}
      {screen === "game" && <GameScreen onVote={() => setScreen("vote")} />}
      {screen === "vote" && <VoteScreen onEliminate={() => setScreen("over")} />}
      {screen === "over" && <GameOverScreen onRestart={() => setScreen("join")} />}
      {screen === "tutorial" && <TutorialScreen onExit={() => setScreen("join")} />}
      {screen === "timeline" && <InteractiveTimelineScreen onRestart={() => setScreen("join")} />}
    </div>
  );
}