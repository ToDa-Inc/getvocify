import { appendFileSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';

export class DiskFullError extends Error {
  constructor() {
    super('No queda espacio para seguir grabando. El audio ya guardado se conserva.');
    this.code = 'ENOSPC';
  }
}

function emptyManifest(clientCaptureId, startedAt) {
  return {
    clientCaptureId,
    startedAt: startedAt || null,
    remoteConfirmed: false,
    audioStatus: 'partial',
    channelsComplete: false,
    channels: {},
  };
}

export class CaptureStore {
  constructor(root, io = {}) {
    this.root = root;
    this.io = {
      appendFile: io.appendFile || appendFileSync,
      mkdir: io.mkdir || mkdirSync,
      readFile: io.readFile || readFileSync,
      writeFile: io.writeFile || writeFileSync,
      readdir: io.readdir || readdirSync,
      rm: io.rm || rmSync,
      exists: io.exists || existsSync,
    };
    this.io.mkdir(root, { recursive: true });
  }

  begin(clientCaptureId, meta = {}) {
    const dir = this.#dir(clientCaptureId);
    this.io.mkdir(dir, { recursive: true });
    const file = this.#manifestPath(clientCaptureId);
    if (!this.io.exists(file)) {
      this.#write(emptyManifest(clientCaptureId, meta.startedAt));
    }
    return this.read(clientCaptureId);
  }

  append(clientCaptureId, channel, chunk) {
    this.begin(clientCaptureId);
    const manifest = this.read(clientCaptureId);
    const current = manifest.channels[channel] || { bytes: 0, absent: false };
    if (current.absent) {
      throw new Error(`El canal ${channel} está marcado como ausente`);
    }
    const audioPath = current.path || path.join(this.#dir(clientCaptureId), `${channel}.bin`);
    try {
      this.io.appendFile(audioPath, chunk);
    } catch (err) {
      if (err && (err.code === 'ENOSPC' || err instanceof DiskFullError)) throw new DiskFullError();
      throw err;
    }
    manifest.channels[channel] = {
      path: audioPath,
      bytes: (current.bytes || 0) + chunk.length,
      absent: false,
    };
    this.#refresh(manifest);
    this.#write(manifest);
    return manifest;
  }

  noteChannelAbsent(clientCaptureId, channel, reason) {
    this.begin(clientCaptureId);
    const manifest = this.read(clientCaptureId);
    const previous = manifest.channels[channel];
    manifest.channels[channel] = {
      ...(previous || {}),
      absent: true,
      reason: reason || 'absent',
    };
    this.#refresh(manifest);
    this.#write(manifest);
    return manifest;
  }

  read(clientCaptureId) {
    return JSON.parse(this.io.readFile(this.#manifestPath(clientCaptureId), 'utf8'));
  }

  pending() {
    return this.io
      .readdir(this.root)
      .map((name) => {
        try {
          return this.read(name);
        } catch {
          return null;
        }
      })
      .filter((row) => row && row.remoteConfirmed === false);
  }

  confirmRemote(clientCaptureId) {
    const manifest = this.read(clientCaptureId);
    manifest.remoteConfirmed = true;
    this.#write(manifest);
    return manifest;
  }

  discard(clientCaptureId) {
    const manifest = this.read(clientCaptureId);
    if (!manifest.remoteConfirmed) {
      throw new Error('No se borra la captura local antes de la confirmación remota');
    }
    this.io.rm(this.#dir(clientCaptureId), { recursive: true, force: true });
  }

  #refresh(manifest) {
    const mic = manifest.channels.mic;
    const system = manifest.channels.system;
    const micOk = Boolean(mic && !mic.absent && mic.bytes > 0);
    const systemOk = Boolean(system && !system.absent && system.bytes > 0);
    manifest.channelsComplete = micOk && systemOk;
    manifest.audioStatus = manifest.channelsComplete ? 'complete' : 'partial';
  }

  #dir(clientCaptureId) {
    return path.join(this.root, clientCaptureId);
  }

  #manifestPath(clientCaptureId) {
    return path.join(this.#dir(clientCaptureId), 'manifest.json');
  }

  #write(manifest) {
    this.io.mkdir(this.#dir(manifest.clientCaptureId), { recursive: true });
    this.io.writeFile(this.#manifestPath(manifest.clientCaptureId), JSON.stringify(manifest));
  }
}
