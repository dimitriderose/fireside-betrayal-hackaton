import { useEffect, useRef, useState, useCallback } from 'react'

// AudioWorklet processor — inlined as a blob; no separate file needed.
// Uses the global `sampleRate` (AudioContext's actual rate) to downsample to 16kHz,
// so the resampling works correctly regardless of the OS audio device rate.
const WORKLET_SRC = `
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this._ratio = sampleRate / 16000
    this._phase = 0
  }
  process(inputs) {
    const channel = inputs[0]?.[0]
    if (!channel || channel.length === 0) return true

    const ratio = this._ratio
    const outputLength = Math.floor((channel.length - this._phase) / ratio)
    if (outputLength <= 0) {
      this._phase -= channel.length
      return true
    }

    const pcm = new Int16Array(outputLength)
    for (let i = 0; i < outputLength; i++) {
      const srcIdx = this._phase + i * ratio
      const lo = Math.floor(srcIdx)
      const hi = Math.min(lo + 1, channel.length - 1)
      const frac = srcIdx - lo
      const sample = channel[lo] * (1 - frac) + channel[hi] * frac
      const s = Math.max(-1, Math.min(1, sample))
      pcm[i] = s < 0 ? s * 32768 : s * 32767
    }
    this._phase = (this._phase + outputLength * ratio) - channel.length
    this.port.postMessage(pcm.buffer, [pcm.buffer])
    return true
  }
}
registerProcessor('pcm-processor', PCMProcessor)
`

const RECONNECT_DELAYS = [500, 1000, 2000, 4000, 8000]
const MAX_RECONNECT_ATTEMPTS = 10 // ~40s total — stop trying after this to save battery
const KEEPALIVE_INTERVAL_MS = 10000 // 10-second keepalive ping

/**
 * Hook for capturing microphone audio, downsampling to 16kHz PCM16,
 * and streaming binary frames via a dedicated audio WebSocket.
 *
 * The audio WS is separate from the game control WS to prevent audio
 * traffic from causing disconnections (matches Amplifi's architecture).
 *
 * Lifecycle split (Fix 1):
 * - WS connects once and stays alive across PTT (push-to-talk) cycles
 * - startCapture() starts mic + AudioContext (connects WS if not already open)
 * - stopCapture() stops mic/worklet/stream only, keeps WS and AudioContext alive
 * - disconnectWs() tears down everything (called when leaving discussion/seance phase)
 */
export function useAudioCapture(gameId, playerId) {
  const [micActive, setMicActive] = useState(false)
  const [micError, setMicError] = useState(null)

  const streamRef = useRef(null)
  const ctxRef = useRef(null)
  const sourceRef = useRef(null)
  const workletRef = useRef(null)
  const audioWsRef = useRef(null)
  const mountedRef = useRef(true)
  const attemptRef = useRef(0)
  const reconnectTimerRef = useRef(null)
  const captureActiveRef = useRef(false) // tracks whether capture is intentionally active
  const reconnectingRef = useRef(false) // Fix 5: prevent races between startCapture and connectAudioWs
  const keepaliveRef = useRef(null) // Fix 3: keepalive interval handle
  const wsConnectedRef = useRef(false) // tracks whether WS is intentionally kept alive

  const buildWsUrl = useCallback(() => {
    const wsBase = import.meta.env.VITE_WS_URL
      ?? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
    return `${wsBase}/ws/audio/${gameId}?playerId=${playerId}`
  }, [gameId, playerId])

  // Fix 3: Start keepalive pings — sends a 1-byte Uint8Array every 10 seconds
  const startKeepalive = useCallback(() => {
    clearInterval(keepaliveRef.current)
    keepaliveRef.current = setInterval(() => {
      if (audioWsRef.current?.readyState === WebSocket.OPEN) {
        audioWsRef.current.send(new Uint8Array([0]))
      }
    }, KEEPALIVE_INTERVAL_MS)
  }, [])

  const stopKeepalive = useCallback(() => {
    clearInterval(keepaliveRef.current)
    keepaliveRef.current = null
  }, [])

  const connectAudioWs = useCallback(() => {
    if (!gameId || !playerId || !mountedRef.current || !wsConnectedRef.current) return

    // Fix 5: Guard against duplicate connections
    if (reconnectingRef.current) return
    if (audioWsRef.current?.readyState === WebSocket.CONNECTING) return
    reconnectingRef.current = true

    // Clean up existing WS
    if (audioWsRef.current) {
      audioWsRef.current.onclose = null
      audioWsRef.current.onerror = null
      audioWsRef.current.close()
      audioWsRef.current = null
    }

    const audioWs = new WebSocket(buildWsUrl())
    audioWs.binaryType = 'arraybuffer'
    audioWsRef.current = audioWs

    audioWs.onopen = () => {
      attemptRef.current = 0
      reconnectingRef.current = false
      // Fix 3: start keepalive pings
      startKeepalive()
    }

    audioWs.onclose = () => {
      audioWsRef.current = null
      reconnectingRef.current = false
      // Fix 3: stop keepalive pings
      stopKeepalive()
      if (!wsConnectedRef.current || !mountedRef.current) return
      if (attemptRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setMicError('Audio connection lost. Tap the mic to reconnect.')
        disconnectWs()
        return
      }
      const delay = RECONNECT_DELAYS[Math.min(attemptRef.current, RECONNECT_DELAYS.length - 1)]
      attemptRef.current++
      reconnectTimerRef.current = setTimeout(connectAudioWs, delay)
    }

    audioWs.onerror = () => audioWs.close()
  }, [gameId, playerId, buildWsUrl, startKeepalive, stopKeepalive])

  const startCapture = useCallback(async () => {
    if (!gameId || !playerId) { stopCapture(); return }
    if (captureActiveRef.current) return // already capturing
    setMicError(null)
    captureActiveRef.current = true

    // Fix 5: Clear any pending reconnect timer before connecting
    clearTimeout(reconnectTimerRef.current)
    reconnectingRef.current = false

    try {
      // Connect WS if not already open (Fix 1: WS persists across PTT cycles)
      if (!audioWsRef.current || audioWsRef.current.readyState !== WebSocket.OPEN) {
        wsConnectedRef.current = true

        // Fix 5: Guard against duplicate connections
        if (audioWsRef.current?.readyState === WebSocket.CONNECTING) {
          // Wait for the existing connection attempt to complete
          await new Promise((resolve, reject) => {
            const existing = audioWsRef.current
            const timer = setTimeout(() => reject(new Error('Audio WebSocket connection timeout')), 5000)
            const origOpen = existing.onopen
            existing.onopen = (e) => { clearTimeout(timer); if (origOpen) origOpen(e); resolve() }
            const origError = existing.onerror
            existing.onerror = (e) => { clearTimeout(timer); if (origError) origError(e); reject(new Error('Audio WebSocket failed to connect')) }
          })
        } else {
          // Open dedicated audio WebSocket (binary mode)
          const audioWs = new WebSocket(buildWsUrl())
          audioWs.binaryType = 'arraybuffer'
          audioWsRef.current = audioWs

          // Wait for WS to open before starting mic capture
          await new Promise((resolve, reject) => {
            const timer = setTimeout(() => reject(new Error('Audio WebSocket connection timeout')), 5000)
            audioWs.onopen = () => {
              clearTimeout(timer)
              attemptRef.current = 0
              reconnectingRef.current = false
              // Fix 3: start keepalive pings
              startKeepalive()
              resolve()
            }
            audioWs.onerror = () => {
              clearTimeout(timer)
              reject(new Error('Audio WebSocket failed to connect'))
            }
          })

          // On WS drop, reconnect (keep mic alive)
          audioWs.onclose = () => {
            audioWsRef.current = null
            reconnectingRef.current = false
            // Fix 3: stop keepalive pings
            stopKeepalive()
            if (!wsConnectedRef.current || !mountedRef.current) return
            if (attemptRef.current >= MAX_RECONNECT_ATTEMPTS) {
              setMicError('Audio connection lost. Tap the mic to reconnect.')
              disconnectWs()
              return
            }
            const delay = RECONNECT_DELAYS[Math.min(attemptRef.current, RECONNECT_DELAYS.length - 1)]
            attemptRef.current++
            reconnectTimerRef.current = setTimeout(connectAudioWs, delay)
          }
          audioWs.onerror = () => audioWs.close()
        }
      }

      // Reuse AudioContext if it already exists (Fix 1: persists across PTT cycles)
      let ctx = ctxRef.current
      if (!ctx || ctx.state === 'closed') {
        ctx = new AudioContext()
        ctxRef.current = ctx

        // Load worklet from blob URL
        const blob = new Blob([WORKLET_SRC], { type: 'application/javascript' })
        const blobUrl = URL.createObjectURL(blob)
        try {
          await ctx.audioWorklet.addModule(blobUrl)
        } finally {
          URL.revokeObjectURL(blobUrl)
        }
      } else if (ctx.state === 'suspended') {
        await ctx.resume()
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      streamRef.current = stream

      const source = ctx.createMediaStreamSource(stream)
      sourceRef.current = source

      const worklet = new AudioWorkletNode(ctx, 'pcm-processor')
      workletRef.current = worklet

      // On each PCM chunk from worklet, send as binary frame
      worklet.port.onmessage = (e) => {
        if (audioWsRef.current?.readyState === WebSocket.OPEN) {
          audioWsRef.current.send(e.data) // ArrayBuffer — binary frame
        }
      }

      source.connect(worklet)
      // Do NOT connect worklet to ctx.destination — prevents mic feedback
      setMicActive(true)
    } catch (err) {
      const msg = err.name === 'NotAllowedError'
        ? 'Microphone permission denied'
        : `Mic error: ${err.message}`
      setMicError(msg)
      captureActiveRef.current = false
      stopCapture()
    }
  }, [gameId, playerId, buildWsUrl, connectAudioWs, startKeepalive, stopKeepalive])

  // Fix 1: stopCapture only stops mic/worklet/stream — keeps WS and AudioContext alive
  const stopCapture = useCallback(() => {
    captureActiveRef.current = false

    // Fix 4: Send end-of-speech signal before stopping mic
    if (audioWsRef.current?.readyState === WebSocket.OPEN) {
      try {
        audioWsRef.current.send(JSON.stringify({ type: 'end_of_speech' }))
      } catch (_) { /* ignore send errors */ }
    }

    if (sourceRef.current) {
      sourceRef.current.disconnect()
      sourceRef.current = null
    }
    if (workletRef.current) {
      workletRef.current.disconnect()
      workletRef.current = null
    }
    // Suspend AudioContext between PTT cycles (saves mobile battery)
    ctxRef.current?.suspend?.()
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    // Do NOT close WebSocket here — it persists across PTT cycles (Fix 1)
    setMicActive(false)
  }, [])

  // Fix 1: disconnectWs tears down everything (WS + AudioContext + mic)
  const disconnectWs = useCallback(() => {
    captureActiveRef.current = false
    wsConnectedRef.current = false
    clearTimeout(reconnectTimerRef.current)
    reconnectingRef.current = false

    // Fix 3: stop keepalive pings
    stopKeepalive()

    if (sourceRef.current) {
      sourceRef.current.disconnect()
      sourceRef.current = null
    }
    if (workletRef.current) {
      workletRef.current.disconnect()
      workletRef.current = null
    }
    if (ctxRef.current) {
      ctxRef.current.close().catch(() => {})
      ctxRef.current = null
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    if (audioWsRef.current) {
      audioWsRef.current.onclose = null // prevent reconnect
      audioWsRef.current.close()
      audioWsRef.current = null
    }
    setMicActive(false)
  }, [stopKeepalive])

  // Page Visibility API: reconnect audio WS when tab becomes visible
  useEffect(() => {
    const handleVisibility = () => {
      if (document.hidden) {
        // Page hidden — proactively close audio WS (it'll die anyway on mobile)
        if (audioWsRef.current) {
          audioWsRef.current.onclose = null // prevent normal reconnect
          audioWsRef.current.close()
          audioWsRef.current = null
        }
        clearTimeout(reconnectTimerRef.current)
        reconnectingRef.current = false
        stopKeepalive()
      } else {
        // Page visible — resume AudioContext (may be suspended by browser) and reconnect WS
        if (wsConnectedRef.current) {
          ctxRef.current?.resume?.()
          if (!audioWsRef.current) {
            attemptRef.current = 0
            connectAudioWs()
          }
        }
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [connectAudioWs, stopKeepalive])

  // Cleanup on unmount
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      disconnectWs()
    }
  }, [disconnectWs])

  return { micActive, micError, startCapture, stopCapture, disconnectWs }
}
