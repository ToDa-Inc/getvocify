import {
  Building2 as Buildings,
  MessagesSquare as ChatsCircle,
  Handshake,
  Search as MagnifyingGlass,
  PhoneIncoming,
  PhoneOutgoing,
  BarChart3 as PresentationChart,
  Target,
  type LucideIcon as Icon,
} from "lucide-react";

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
