/**
 * useRealtimeTranscription Hook
 * 
 * Manages WebSocket connection to backend for real-time transcription.
 * Streams audio from microphone to backend, receives transcripts in real-time.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import type { UseRealtimeTranscriptionReturn, ProviderTranscript } from '../types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8888/api/v1';
const WS_BASE = API_URL.replace(/^http/, 'ws').replace(/\/api\/v1\/?$/, '');

/**
 * Hook for real-time transcription via WebSocket (Dual-Streaming)
 */
export function useRealtimeTranscription(
  userId: string,
  language: 'multi' | 'en' | 'es' = 'multi'
): UseRealtimeTranscriptionReturn {
  // Connection state
  const [isConnected, setIsConnected] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Provider state (Speechmatics only - Deepgram removed)
  const [providerTranscripts, setProviderTranscripts] = useState<Record<string, ProviderTranscript>>({
    speechmatics: { interim: '', final: '', full: '' }
  });
  
  // Refs
  const websocketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<AudioWorkletNode | ScriptProcessorNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const keepAliveIntervalRef = useRef<number | null>(null);
  const isStoppingRef = useRef(false);

  // Cleanup function
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
      } catch (e) {}
      websocketRef.current = null;
    }
    
    if (processorRef.current) {
      try {
        processorRef.current.disconnect();
      } catch (e) {}
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

  const start = useCallback(async (existingStream?: MediaStream) => {
    if (isTranscribing) return;

    try {
      setError(null);
      setIsTranscribing(true);
      isStoppingRef.current = false;

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
            console.log('Dual-stream proxy connected');
            return;
          }

          if (data.type === 'Results') {
            const provider = data.provider || 'speechmatics';
            if (provider === 'deepgram') return; // Deepgram removed from recording page
            const transcript = data.channel?.alternatives?.[0]?.transcript || '';
            const isFinal = data.is_final || data.speech_final;
            
            if (!transcript) return;

            setProviderTranscripts(prev => {
              const current = prev[provider] || { interim: '', final: '', full: '' };
              let nextFinal = current.final;
              let nextInterim = current.interim;

              if (isFinal) {
                nextFinal = nextFinal ? `${nextFinal} ${transcript}` : transcript;
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
                  full: nextFull
                }
              };
            });
          }

          if (data.type === 'error') {
            setError(data.message || 'Transcription error');
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
      (processorRef.current as any) = workletNode;

      workletNode.port.onmessage = (event) => {
        const currentWs = websocketRef.current;
        if (currentWs && currentWs.readyState === WebSocket.OPEN) {
          currentWs.send(event.data);
        }
      };

      source.connect(workletNode);
      workletNode.connect(audioContext.destination);

    } catch (err) {
      console.error('Failed to start transcription:', err);
      setError('Failed to start transcription');
      setIsTranscribing(false);
      cleanup();
    }
  }, [userId, language, isTranscribing, cleanup]);

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

  const reset = useCallback(() => {
    cleanup();
    setProviderTranscripts({
      speechmatics: { interim: '', final: '', full: '' }
    });
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
    start,
    stop,
    reset,
  };
}

