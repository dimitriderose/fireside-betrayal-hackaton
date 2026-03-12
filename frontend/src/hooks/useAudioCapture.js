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

/**
 * Hook for capturing microphone audio, downsampling to 16kHz PCM16,
 * and streaming binary frames via a dedicated audio WebSocket.
 *
 * The audio WS is separate from the game control WS to prevent audio
 * traffic from causing disconnections (matches Amplifi's architecture).
 */
export function useAudioCapture(gameId, playerId) {
  const [micActive, setMicActive] = useState(false)
  const [micError, setMicError] = useState(null)

  const streamRef = useRef(null)
  const ctxRef = useRef(null)
  const sourceRef = useRef(null)
  const workletRef = useRef(null)
  const audioWsRef = useRef(null)

  const startCapture = useCallback(async () => {
    if (!gameId || !playerId) { stopCapture(); return } // no valid session — clean up any active capture
    if (streamRef.current) return // already capturing
    setMicError(null)

    try {
      // Open dedicated audio WebSocket (binary mode)
      const wsBase = import.meta.env.VITE_WS_URL
        ?? `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
      const wsUrl = `${wsBase}/ws/audio/${gameId}?playerId=${playerId}`
      const audioWs = new WebSocket(wsUrl)
      audioWs.binaryType = 'arraybuffer'
      audioWsRef.current = audioWs

      // Wait for WS to open before starting mic capture
      await new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('Audio WebSocket connection timeout')), 5000)
        audioWs.onopen = () => { clearTimeout(timer); resolve() }
        audioWs.onerror = () => { clearTimeout(timer); reject(new Error('Audio WebSocket failed to connect')) }
      })

      // Auto-cleanup if audio WS drops mid-capture
      audioWs.onclose = () => stopCapture()
      audioWs.onerror = () => stopCapture()

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })
      streamRef.current = stream

      const ctx = new AudioContext()
      ctxRef.current = ctx

      // Load worklet from blob URL
      const blob = new Blob([WORKLET_SRC], { type: 'application/javascript' })
      const blobUrl = URL.createObjectURL(blob)
      try {
        await ctx.audioWorklet.addModule(blobUrl)
      } finally {
        URL.revokeObjectURL(blobUrl)
      }

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
      // Clean up partial state on error
      stopCapture()
    }
  }, [gameId, playerId])

  const stopCapture = useCallback(() => {
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
      audioWsRef.current.close()
      audioWsRef.current = null
    }
    setMicActive(false)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => stopCapture()
  }, [stopCapture])

  return { micActive, micError, startCapture, stopCapture }
}
