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
 * and streaming base64-encoded chunks via the game WebSocket.
 */
export function useAudioCapture(sendMessage) {
  const [micActive, setMicActive] = useState(false)
  const [muted, setMuted] = useState(false)
  const [micError, setMicError] = useState(null)

  const streamRef = useRef(null)
  const ctxRef = useRef(null)
  const sourceRef = useRef(null)
  const workletRef = useRef(null)
  const mutedRef = useRef(false)

  // Keep mutedRef in sync so the worklet callback closure sees current value
  mutedRef.current = muted

  const startCapture = useCallback(async () => {
    if (streamRef.current) return // already capturing
    setMicError(null)

    try {
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

      // On each PCM chunk from worklet, base64-encode and send via WS
      worklet.port.onmessage = (e) => {
        if (mutedRef.current) return
        const bytes = new Uint8Array(e.data)
        let binary = ''
        for (let i = 0; i < bytes.length; i++) {
          binary += String.fromCharCode(bytes[i])
        }
        const b64 = btoa(binary)
        sendMessage('player_audio', { audio: b64 })
      }

      source.connect(worklet)
      // Do NOT connect worklet to ctx.destination — prevents mic feedback
      setMicActive(true)
    } catch (err) {
      const msg = err.name === 'NotAllowedError'
        ? 'Microphone permission denied'
        : `Mic error: ${err.message}`
      setMicError(msg)
    }
  }, [sendMessage])

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
    setMicActive(false)
  }, [])

  const toggleMute = useCallback(() => {
    setMuted(prev => !prev)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => stopCapture()
  }, [stopCapture])

  return { micActive, muted, micError, startCapture, stopCapture, toggleMute }
}
