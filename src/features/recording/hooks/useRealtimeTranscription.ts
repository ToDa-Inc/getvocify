/**
 * useRealtimeTranscription Hook
 *
 * Manages WebSocket connection to backend for real-time transcription.
 * Streams audio from microphone to backend, receives transcripts in real-time.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import type {
  UseRealtimeTranscriptionReturn,
  ProviderTranscript,
  RealtimeTranscriptionOptions,
  TranscriptWord,
} from '../types';
import {
  applyLiveResults,
  cloneAudioStream,
  EMPTY_TRANSCRIPT,
  LIVE_STT_SAMPLE_RATE,
  PCM_WORKLET_SOURCE,
  stopMediaStream,
} from '../live-stt';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8888/api/v1';
const WS_BASE = API_URL.replace(/^http/, 'ws').replace(/\/api\/v1\/?$/, '');

/**
 * Hook for real-time transcription via WebSocket
 */
export function useRealtimeTranscription(
  userId: string,
  language: 'multi' | 'en' | 'es' = 'multi',
  options: RealtimeTranscriptionOptions = {}
): UseRealtimeTranscriptionReturn {
  const mode = options.mode || 'default';
  const onSpeakersResultRef = useRef(options.onSpeakersResult);
  onSpeakersResultRef.current = options.onSpeakersResult;

  const [isConnected, setIsConnected] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [transcriptState, setTranscriptState] = useState<ProviderTranscript>(EMPTY_TRANSCRIPT);
  const [providerTranscripts, setProviderTranscripts] = useState<
    Record<string, ProviderTranscript>
  >({});
  const [finalWords, setFinalWords] = useState<TranscriptWord[]>([]);
  const [pendingSpeakerIdentifiers, setPendingSpeakerIdentifiers] = useState<
    string[] | null
  >(null);
  const [endOfUtteranceSeq, setEndOfUtteranceSeq] = useState(0);

  const websocketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<AudioWorkletNode | ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const ownsStreamRef = useRef(false);
  const sessionActiveRef = useRef(false);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const keepAliveIntervalRef = useRef<number | null>(null);
  const isStoppingRef = useRef(false);

  const teardownGraph = useCallback(() => {
    if (processorRef.current) {
      try {
        processorRef.current.disconnect();
      } catch {
        /* ignore */
      }
      processorRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
  }, []);

  const cleanup = useCallback((isManualStop = false) => {
    if (isManualStop && websocketRef.current?.readyState === WebSocket.OPEN) {
      isStoppingRef.current = true;
      websocketRef.current.send(JSON.stringify({ type: 'CloseStream' }));
      return;
    }

    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (keepAliveIntervalRef.current) {
      clearInterval(keepAliveIntervalRef.current);
      keepAliveIntervalRef.current = null;
    }

    if (websocketRef.current) {
      try {
        websocketRef.current.onclose = null;
        websocketRef.current.close();
      } catch {
        /* ignore */
      }
      websocketRef.current = null;
    }

    teardownGraph();

    if (ownsStreamRef.current) {
      stopMediaStream(streamRef.current);
    }
    streamRef.current = null;
    ownsStreamRef.current = false;
    sessionActiveRef.current = false;
    setIsConnected(false);
    setIsTranscribing(false);
    isStoppingRef.current = false;
  }, [teardownGraph]);

  useEffect(() => {
    return () => cleanup(false);
  }, [cleanup]);

  const attachPcmWorklet = useCallback(async (stream: MediaStream) => {
    const audioContext = new AudioContext({ sampleRate: LIVE_STT_SAMPLE_RATE });
    audioContextRef.current = audioContext;
    if (audioContext.state === 'suspended') await audioContext.resume();

    const blob = new Blob([PCM_WORKLET_SOURCE], { type: 'application/javascript' });
    const moduleUrl = URL.createObjectURL(blob);
    await audioContext.audioWorklet.addModule(moduleUrl);
    URL.revokeObjectURL(moduleUrl);

    const source = audioContext.createMediaStreamSource(stream);
    const workletNode = new AudioWorkletNode(audioContext, 'pcm-processor');
    processorRef.current = workletNode;

    workletNode.port.onmessage = (evt) => {
      const currentWs = websocketRef.current;
      if (currentWs && currentWs.readyState === WebSocket.OPEN) {
        currentWs.send(evt.data);
      }
    };

    // Keep the graph alive without playing mic into speakers (critical for phone-on-speaker).
    const mute = audioContext.createGain();
    mute.gain.value = 0;
    source.connect(workletNode);
    workletNode.connect(mute);
    mute.connect(audioContext.destination);
  }, []);

  const start = useCallback(
    async (existingStream?: MediaStream) => {
      if (sessionActiveRef.current) return;

      try {
        setError(null);
        setIsTranscribing(true);
        sessionActiveRef.current = true;
        isStoppingRef.current = false;
        setPendingSpeakerIdentifiers(null);

        let stream: MediaStream;
        if (existingStream) {
          const alreadyOwned =
            ownsStreamRef.current && streamRef.current === existingStream;
          if (alreadyOwned) {
            stream = existingStream;
          } else {
            stream = cloneAudioStream(existingStream);
            ownsStreamRef.current = true;
          }
        } else {
          stream = await navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
              sampleRate: LIVE_STT_SAMPLE_RATE,
            },
          });
          ownsStreamRef.current = true;
        }
        streamRef.current = stream;

        const wsUrl = new URL(`${WS_BASE}/api/v1/transcription/live`);
        wsUrl.searchParams.set('user_id', userId);
        wsUrl.searchParams.set('language', language);
        if (mode && mode !== 'default') {
          wsUrl.searchParams.set('mode', mode);
        }

        const ws = new WebSocket(wsUrl.toString());
        ws.binaryType = 'arraybuffer';
        websocketRef.current = ws;

        ws.onopen = () => {
          setIsConnected(true);
          setError(null);
          keepAliveIntervalRef.current = window.setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'KeepAlive' }));
            }
          }, 5000);
          attachPcmWorklet(stream).catch((err) => {
            console.error('Failed to attach PCM worklet:', err);
            setError('Failed to start live transcription');
          });
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);

            if (data.type === 'connected') {
              return;
            }

            if (data.type === 'EndOfUtterance') {
              setEndOfUtteranceSeq((n) => n + 1);
              return;
            }

            if (data.type === 'SpeakersResult') {
              const ids = Array.isArray(data.speaker_identifiers)
                ? data.speaker_identifiers.filter(
                    (x: unknown) => typeof x === 'string' && x.trim()
                  )
                : [];
              setPendingSpeakerIdentifiers(ids);
              onSpeakersResultRef.current?.(ids);
              return;
            }

            if (data.type === 'Results') {
              const provider = data.provider || 'default';
              const words: TranscriptWord[] = Array.isArray(data.words)
                ? data.words.map(
                    (w: {
                      text?: string;
                      speaker?: string | null;
                      is_punct?: boolean;
                    }) => ({
                      text: String(w.text || ''),
                      speaker: w.speaker ? String(w.speaker) : null,
                      is_punct: Boolean(w.is_punct),
                    })
                  )
                : [];

              const next = applyLiveResults(EMPTY_TRANSCRIPT, data);
              if (!next) return;

              if ((data.is_final || data.speech_final) && words.length > 0) {
                setFinalWords((prev) => [...prev, ...words.filter((w) => w.text)]);
              }

              setTranscriptState((prev) => applyLiveResults(prev, data) || prev);

              setProviderTranscripts((prev) => {
                const current = prev[provider] || EMPTY_TRANSCRIPT;
                const updated = applyLiveResults(current, data);
                if (!updated) return prev;
                return { ...prev, [provider]: updated };
              });
            }

            if (data.type === 'error' || data.type === 'Error') {
              setError(data.message || data.error || 'Transcription error');
            }
          } catch (e) {
            console.error('Error parsing WebSocket message:', e);
          }
        };

        ws.onerror = () => {
          setError('Connection error');
          setIsConnected(false);
        };

        ws.onclose = (event) => {
          setIsConnected(false);
          if (keepAliveIntervalRef.current) {
            clearInterval(keepAliveIntervalRef.current);
            keepAliveIntervalRef.current = null;
          }

          if (isStoppingRef.current || event.code === 1000) {
            setIsTranscribing(false);
            sessionActiveRef.current = false;
            isStoppingRef.current = false;
            teardownGraph();
          } else if (sessionActiveRef.current) {
            const replay = streamRef.current;
            sessionActiveRef.current = false;
            teardownGraph();
            reconnectTimeoutRef.current = window.setTimeout(() => {
              start(replay || undefined);
            }, 2000);
          }
        };
      } catch (err) {
        console.error('Failed to start transcription:', err);
        setError('Failed to start transcription');
        setIsTranscribing(false);
        cleanup();
      }
    },
    [userId, language, mode, attachPcmWorklet, cleanup, teardownGraph]
  );

  const stop = useCallback(() => {
    if (!sessionActiveRef.current && !isTranscribing) return;
    if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
      isStoppingRef.current = true;
      websocketRef.current.send(JSON.stringify({ type: 'Finalize' }));
      websocketRef.current.send(JSON.stringify({ type: 'CloseStream' }));
      teardownGraph();
    } else {
      cleanup(false);
    }
  }, [isTranscribing, cleanup, teardownGraph]);

  const forceEndOfUtterance = useCallback(() => {
    const ws = websocketRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ForceEndOfUtterance' }));
    }
  }, []);

  const reset = useCallback(() => {
    cleanup();
    setTranscriptState(EMPTY_TRANSCRIPT);
    setProviderTranscripts({});
    setFinalWords([]);
    setPendingSpeakerIdentifiers(null);
    setEndOfUtteranceSeq(0);
    setError(null);
  }, [cleanup]);

  return {
    isConnected,
    isTranscribing,
    error,
    interimTranscript: transcriptState.interim,
    finalTranscript: transcriptState.final,
    fullTranscript: transcriptState.full,
    providerTranscripts,
    finalWords,
    pendingSpeakerIdentifiers,
    endOfUtteranceSeq,
    forceEndOfUtterance,
    start,
    stop,
    reset,
  };
}
