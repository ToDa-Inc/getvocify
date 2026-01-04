/**
 * Offscreen Document - Audio Recording + Deepgram Streaming
 * 
 * This document handles:
 * 1. Microphone access (getUserMedia)
 * 2. Raw PCM audio capture via AudioContext
 * 3. WebSocket streaming to backend for real-time transcription
 * 4. Final audio recording via MediaRecorder for upload
 */

const WS_URL = 'ws://localhost:8888/api/v1/transcription/live?language=multi';

let mediaRecorder = null;
let audioChunks = [];
let stream = null;
let audioContext = null;
let processor = null;
let websocket = null;

/**
 * Convert Float32 audio samples to Int16 PCM
 */
function float32ToInt16(float32Array) {
  const int16Array = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  return int16Array.buffer;
}

/**
 * Start recording with real-time transcription
 */
async function startRecording() {
  try {
    // 1. Get microphone stream
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    // 2. Setup MediaRecorder for final audio file
    const recorderOptions = { mimeType: 'audio/webm;codecs=opus' };
    if (!MediaRecorder.isTypeSupported(recorderOptions.mimeType)) {
      delete recorderOptions.mimeType;
    }
    mediaRecorder = new MediaRecorder(stream, recorderOptions);
    audioChunks = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) audioChunks.push(event.data);
    };

    mediaRecorder.onstop = () => {
      const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
      const reader = new FileReader();
      reader.onloadend = () => {
        chrome.runtime.sendMessage({
          type: 'RECORDING_COMPLETE',
          audioData: reader.result,
        });
      };
      reader.readAsDataURL(audioBlob);

      // Cleanup stream
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
      }
    };

    // 3. Setup WebSocket for real-time transcription
    websocket = new WebSocket(WS_URL);
    
    websocket.onopen = () => {
      console.log('[Offscreen] WebSocket connected to backend');
    };

    websocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.type === 'connected') {
          console.log('[Offscreen] Transcription session started');
          return;
        }

        if (data.type === 'Results') {
          const transcript = data.channel?.alternatives?.[0]?.transcript || '';
          const isFinal = data.is_final || data.speech_final;
          
          if (transcript) {
            chrome.runtime.sendMessage({
              type: 'TRANSCRIPT_UPDATE',
              text: transcript,
              isFinal: isFinal,
              provider: data.provider || 'deepgram'
            });
          }
        }
      } catch (e) {
        console.error('[Offscreen] Error parsing message:', e);
      }
    };

    websocket.onerror = (error) => {
      console.error('[Offscreen] WebSocket error:', error);
    };

    websocket.onclose = () => {
      console.log('[Offscreen] WebSocket closed');
    };

    // 4. Setup AudioContext for raw PCM streaming
    audioContext = new AudioContext({ sampleRate: 16000 });
    const source = audioContext.createMediaStreamSource(stream);
    
    // ScriptProcessorNode for raw PCM access
    processor = audioContext.createScriptProcessor(4096, 1, 1);
    
    processor.onaudioprocess = (e) => {
      if (websocket && websocket.readyState === WebSocket.OPEN) {
        const inputData = e.inputBuffer.getChannelData(0);
        const pcmData = float32ToInt16(inputData);
        websocket.send(pcmData);
      }
    };

    source.connect(processor);
    processor.connect(audioContext.destination);

    // 5. Start MediaRecorder
    mediaRecorder.start(100);
    
    chrome.runtime.sendMessage({ type: 'RECORDING_STARTED' });
    console.log('[Offscreen] Recording started');

  } catch (error) {
    console.error('[Offscreen] Recording error:', error);
    chrome.runtime.sendMessage({
      type: 'RECORDING_ERROR',
      error: error.message || 'Failed to start recording. Check mic permissions.',
    });
  }
}

/**
 * Stop recording
 */
function stopRecording() {
  console.log('[Offscreen] Stopping recording...');
  
  // Stop processor
  if (processor) {
    processor.disconnect();
    processor = null;
  }

  // Close WebSocket
  if (websocket) {
    if (websocket.readyState === WebSocket.OPEN) {
      websocket.send(JSON.stringify({ type: 'CloseStream' }));
    }
    websocket.close();
    websocket = null;
  }

  // Close AudioContext
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }

  // Stop MediaRecorder (triggers onstop → sends RECORDING_COMPLETE)
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
}

/**
 * Message listener
 */
chrome.runtime.onMessage.addListener((message) => {
  if (message.target !== 'offscreen') return;

  switch (message.type) {
    case 'START_RECORDING':
      startRecording();
      break;
    case 'STOP_RECORDING':
      stopRecording();
      break;
  }
});
