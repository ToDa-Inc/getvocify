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

  const [providerTranscripts, setProviderTranscripts] = useState<
    Record<string, ProviderTranscript>
  >({
    speechmatics: { interim: '', final: '', full: '' },
  });
  const [finalWords, setFinalWords] = useState<TranscriptWord[]>([]);
  const [pendingSpeakerIdentifiers, setPendingSpeakerIdentifiers] = useState<
    string[] | null
  >(null);
  const [endOfUtteranceSeq, setEndOfUtteranceSeq] = useState(0);

  const websocketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<AudioWorkletNode | ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const keepAliveIntervalRef = useRef<number | null>(null);
  const isStoppingRef = useRef(false);

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

    streamRef.current = null;
    setIsConnected(false);
    setIsTranscribing(false);
    isStoppingRef.current = false;
  }, []);

  useEffect(() => {
    return () => cleanup(false);
  }, [cleanup]);

  const start = useCallback(
    async (existingStream?: MediaStream) => {
      if (isTranscribing) return;

      try {
        setError(null);
        setIsTranscribing(true);
        isStoppingRef.current = false;
        setPendingSpeakerIdentifiers(null);

        let stream = existingStream;
        if (!stream) {
          stream = await navigator.mediaDevices.getUserMedia({
            audio: {
              echoCancellation: true,
              noiseSuppression: true,
              autoGainControl: true,
              sampleRate: 16000,
            },
          });
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
              const provider = data.provider || 'speechmatics';
              if (provider === 'deepgram') return;
              const transcript = data.channel?.alternatives?.[0]?.transcript || '';
              const isFinal = data.is_final || data.speech_final;
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

              if (!transcript && words.length === 0) return;

              if (isFinal && words.length > 0) {
                setFinalWords((prev) => [...prev, ...words.filter((w) => w.text)]);
              }

              setProviderTranscripts((prev) => {
                const current = prev[provider] || { interim: '', final: '', full: '' };
                let nextFinal = current.final;
                let nextInterim = current.interim;

                if (isFinal) {
                  const piece =
                    transcript ||
                    words
                      .filter((w) => !w.is_punct)
                      .map((w) => w.text)
                      .join(' ');
                  if (piece) {
                    nextFinal = nextFinal ? `${nextFinal} ${piece}` : piece;
                  }
                  nextInterim = '';
                } else {
                  nextInterim = transcript;
                }

                const nextFull = `${nextFinal}${nextInterim ? ` ${nextInterim}` : ''}`.trim();

                return {
                  ...prev,
                  [provider]: {
                    final: nextFinal,
                    interim: nextInterim,
                    full: nextFull,
                  },
                };
              });
            }

            if (data.type === 'error' || data.type === 'Error') {
              setError(data.message || data.error || 'Transcription error');
              setIsTranscribing(false);
            }
          } catch (e) {
            console.error('Error parsing WebSocket message:', e);
          }
        };

        ws.onerror = () => {
          setError('Connection error');
          setIsTranscribing(false);
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
            isStoppingRef.current = false;
            if (processorRef.current) {
              processorRef.current.disconnect();
              processorRef.current = null;
            }
            if (audioContextRef.current) {
              audioContextRef.current.close().catch(() => {});
              audioContextRef.current = null;
            }
          } else if (isTranscribing) {
            reconnectTimeoutRef.current = window.setTimeout(() => {
              start(streamRef.current || undefined);
            }, 2000);
          }
        };

        const audioContext = new AudioContext({ sampleRate: 16000 });
        audioContextRef.current = audioContext;
        if (audioContext.state === 'suspended') await audioContext.resume();

        const processorCode = `
        class PcmProcessor extends AudioWorkletProcessor {
          process(inputs) {
            const input = inputs[0];
            if (input && input.length > 0) {
              const channelData = input[0];
              const int16Array = new Int16Array(channelData.length);
              for (let i = 0; i < channelData.length; i++) {
                const s = Math.max(-1, Math.min(1, channelData[i]));
                int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
              }
              this.port.postMessage(int16Array.buffer, [int16Array.buffer]);
            }
            return true;
          }
        }
        registerProcessor('pcm-processor', PcmProcessor);
      `;

        const blob = new Blob([processorCode], { type: 'application/javascript' });
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
      } catch (err) {
        console.error('Failed to start transcription:', err);
        setError('Failed to start transcription');
        setIsTranscribing(false);
        cleanup();
      }
    },
    [userId, language, mode, isTranscribing, cleanup]
  );

  const stop = useCallback(() => {
    if (!isTranscribing) return;
    if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
      isStoppingRef.current = true;
      websocketRef.current.send(JSON.stringify({ type: 'Finalize' }));
      websocketRef.current.send(JSON.stringify({ type: 'CloseStream' }));
      if (processorRef.current) {
        processorRef.current.disconnect();
        processorRef.current = null;
      }
    } else {
      cleanup(false);
    }
  }, [isTranscribing, cleanup]);

  const forceEndOfUtterance = useCallback(() => {
    const ws = websocketRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ForceEndOfUtterance' }));
    }
  }, []);

  const reset = useCallback(() => {
    cleanup();
    setProviderTranscripts({
      speechmatics: { interim: '', final: '', full: '' },
    });
    setFinalWords([]);
    setPendingSpeakerIdentifiers(null);
    setEndOfUtteranceSeq(0);
    setError(null);
  }, [cleanup]);

  return {
    isConnected,
    isTranscribing,
    error,
    interimTranscript: providerTranscripts.speechmatics.interim,
    finalTranscript: providerTranscripts.speechmatics.final,
    fullTranscript: providerTranscripts.speechmatics.full,
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
