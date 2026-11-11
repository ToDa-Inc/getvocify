/**
 * The name above a bubble from the other side, when the backend told that side's voices apart. It is also the
 * control for getting a voice wrong: rename it, say it is the same person as another voice, or move the paragraph
 * to another voice (or to someone new).
 */

import { useRef, useState } from 'react';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { useLanguage } from '@/lib/i18n';
import type { MeetingDisplayTurn, MeetingVoice } from '@/lib/meeting-transcript';
import type { VoiceAction } from '@/lib/voice-actions';

const WORDS = {
  EN: { name: 'Name this voice', menu: 'rename, merge or move', rename: 'Rename', same: 'Same person as', move: 'Move this to', someone: 'Someone new' },
  ES: { name: 'Nombra esta voz', menu: 'renombrar, unir o mover', rename: 'Renombrar', same: 'Misma persona que', move: 'Mover a', someone: 'Otra persona' },
};

interface VoiceLabelProps {
  turn: MeetingDisplayTurn;
  voices: MeetingVoice[];
  onChange: (action: VoiceAction) => void;
}

export function VoiceLabel({ turn, voices, onChange }: VoiceLabelProps) {
  const words = WORDS[useLanguage().language];
  const voice = turn.voice as number;
  const label = turn.label ?? '';
  const others = voices.filter((other) => other.id !== voice);
  const starts = turn.starts ?? [];
  const [renaming, setRenaming] = useState(false);
  const cancelled = useRef(false);

  const finish = (name: string) => {
    setRenaming(false);
    if (cancelled.current) {
      cancelled.current = false;
      return;
    }
    // Leaving it as it reads changes nothing; emptying it goes back to the default.
    if (name.trim() !== label) onChange({ op: 'rename', voice, name });
  };

  if (renaming) {
    return (
      <Input
        autoFocus
        defaultValue={turn.name ?? ''}
        placeholder={label}
        maxLength={60}
        aria-label={words.name}
        className="h-6 w-36 px-1.5 text-[11px] font-medium"
        onFocus={(event) => event.currentTarget.select()}
        onBlur={(event) => finish(event.currentTarget.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur();
          if (event.key === 'Escape') {
            cancelled.current = true;
            event.currentTarget.blur();
          }
        }}
      />
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={`${label}: ${words.menu}`}
        className="rounded px-1 text-[11px] font-medium text-beige outline-none transition-colors hover:bg-muted/60 focus-visible:ring-1 focus-visible:ring-ring"
      >
        {label}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-40">
        <DropdownMenuItem onSelect={() => setRenaming(true)}>{words.rename}</DropdownMenuItem>
        {others.length ? (
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>{words.same}</DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              {others.map((other) => (
                <DropdownMenuItem key={other.id} onSelect={() => onChange({ op: 'merge', keep: other.id, drop: voice })}>
                  {other.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        ) : null}
        {starts.length ? (
          <DropdownMenuSub>
            <DropdownMenuSubTrigger>{words.move}</DropdownMenuSubTrigger>
            <DropdownMenuSubContent>
              {others.map((other) => (
                <DropdownMenuItem key={other.id} onSelect={() => onChange({ op: 'move', starts, voice: other.id })}>
                  {other.label}
                </DropdownMenuItem>
              ))}
              {others.length ? <DropdownMenuSeparator /> : null}
              <DropdownMenuItem onSelect={() => onChange({ op: 'move', starts, voice: null })}>{words.someone}</DropdownMenuItem>
            </DropdownMenuSubContent>
          </DropdownMenuSub>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
