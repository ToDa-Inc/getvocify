/**
 * The name above a bubble from the other side, when the backend told that side's voices apart. One click lists the
 * people in the meeting (from the calendar, and names already given): picking one names this voice, and picking a name
 * another voice has makes them one person. "Someone else" types a name.
 */

import { useRef, useState } from 'react';
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { useLanguage } from '@/lib/i18n';
import type { MeetingDisplayTurn, MeetingVoice } from '@/lib/meeting-transcript';
import { pickName, voiceNames, type VoiceAction } from '@/lib/voice-actions';

const WORDS = {
  EN: { name: 'Name this voice', menu: 'who is this?', someone: 'Someone else…' },
  ES: { name: 'Nombra esta voz', menu: '¿quién es?', someone: 'Otra persona…' },
};

interface VoiceLabelProps {
  turn: MeetingDisplayTurn;
  voices: MeetingVoice[];
  /** Who the calendar says is in the meeting, besides the rep. */
  people?: string[];
  onChange: (action: VoiceAction) => void;
}

export function VoiceLabel({ turn, voices, people = [], onChange }: VoiceLabelProps) {
  const words = WORDS[useLanguage().language];
  const voice = turn.voice as number;
  const label = turn.label ?? '';
  const names = voiceNames(voices, people);
  const [renaming, setRenaming] = useState(false);
  const cancelled = useRef(false);

  const choose = (name: string) => {
    const action = pickName(voices, voice, name);
    if (action) onChange(action);
  };

  const finish = (name: string) => {
    setRenaming(false);
    if (cancelled.current) {
      cancelled.current = false;
      return;
    }
    choose(name);
  };

  if (renaming) {
    return (
      <Input
        autoFocus
        placeholder={label}
        maxLength={60}
        aria-label={words.name}
        className="h-6 w-36 px-1.5 text-[11px] font-medium"
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
        {names.map((name) => (
          <DropdownMenuCheckboxItem
            key={name}
            checked={name.trim().toLowerCase() === label.trim().toLowerCase()}
            onSelect={() => choose(name)}
          >
            {name}
          </DropdownMenuCheckboxItem>
        ))}
        {names.length ? <DropdownMenuSeparator /> : null}
        <DropdownMenuItem onSelect={() => setRenaming(true)}>{words.someone}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
