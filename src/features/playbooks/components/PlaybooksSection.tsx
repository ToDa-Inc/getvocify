import { PlaybookList } from "@/features/playbooks/components/PlaybookList";

/**
 * Ajustes → Playbooks e interacciones: one place to give Vocify the playbook, one row per
 * interaction type and the reserved Interna row (docs/superpowers/plans/2026-09-29-playbooks-v2.md
 * §14). Setup is the company's own document, file or voice note, which Vocify structures.
 */
export default function PlaybooksSection() {
  return <PlaybookList />;
}
