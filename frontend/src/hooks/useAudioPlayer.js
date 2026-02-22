import { useEffect, useRef, useState, useCallback } from 'react'

/**
 * Plays PCM audio chunks received from the Narrator via WebSocket.
 * Audio spec: 24000 Hz, 16-bit signed int, mono.
 * Chunks arrive as base64-encoded strings and are scheduled seamlessly.
 */
export function useAudioPlayer() {
  const ctxRef = useRef(null)
  const gainRef = useRef(null)
  const nextTimeRef = useRef(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [volume, setVolumeState] = useState(1.0)

  const getCtx = useCallback(() => {
    if (!ctxRef.current || ctxRef.current.state === 'closed') {
      ctxRef.current = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 24000 })
      gainRef.current = ctxRef.current.createGain()
      gainRef.current.gain.value = volume
      gainRef.current.connect(ctxRef.current.destination)
    }
    if (ctxRef.current.state === 'suspended') ctxRef.current.resume()
    return ctxRef.current
  }, [volume])

  const playChunk = useCallback((base64PCM) => {
    try {
      const ctx = getCtx()

      // Decode base64 → Uint8Array
      const binary = atob(base64PCM)
      const bytes = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)

      // Convert 16-bit LE PCM → Float32
      const numSamples = bytes.length / 2
      const float32 = new Float32Array(numSamples)
      const view = new DataView(bytes.buffer)
      for (let i = 0; i < numSamples; i++) {
        float32[i] = view.getInt16(i * 2, true) / 32768.0
      }

      const buffer = ctx.createBuffer(1, numSamples, 24000)
      buffer.copyToChannel(float32, 0)

      const source = ctx.createBufferSource()
      source.buffer = buffer
      source.connect(gainRef.current)

      const now = ctx.currentTime
      const startAt = Math.max(now, nextTimeRef.current)
      source.start(startAt)
      nextTimeRef.current = startAt + buffer.duration

      setIsPlaying(true)
      source.onended = () => {
        if (nextTimeRef.current <= ctx.currentTime + 0.05) setIsPlaying(false)
      }
    } catch (err) {
      console.error('[useAudioPlayer] playback error:', err)
    }
  }, [getCtx])

  const setVolume = useCallback((v) => {
    setVolumeState(v)
    if (gainRef.current) gainRef.current.gain.value = v
  }, [])

  // Listen for audio relayed from useWebSocket
  useEffect(() => {
    const handler = (e) => playChunk(e.detail)
    window.addEventListener('narrator-audio', handler)
    return () => window.removeEventListener('narrator-audio', handler)
  }, [playChunk])

  return { playChunk, isPlaying, volume, setVolume }
}
