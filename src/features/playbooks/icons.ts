import {
  Buildings,
  ChatsCircle,
  Handshake,
  MagnifyingGlass,
  PhoneIncoming,
  PhoneOutgoing,
  PresentationChart,
  Target,
  type Icon,
} from "@phosphor-icons/react";

/** One icon per catalog call type, so the list is scannable before it is read. */
const CALL_TYPE_ICONS: Record<string, Icon> = {
  discovery: PhoneOutgoing,
  inbound: PhoneIncoming,
  ae_discovery: MagnifyingGlass,
  closing: PresentationChart,
  negotiation: Handshake,
  qualification: Target,
};

export function callTypeIcon(key: string): Icon {
  return CALL_TYPE_ICONS[key] ?? ChatsCircle;
}

export const CompanyIcon = Buildings;
