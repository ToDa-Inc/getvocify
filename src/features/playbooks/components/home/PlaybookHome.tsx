import { CompanyBlock, type CompanyAreaState } from "@/features/playbooks/components/home/CompanyBlock";
import { FunnelBlock, type HomeType } from "@/features/playbooks/components/home/FunnelBlock";
import { OtherCalls } from "@/features/playbooks/components/home/OtherCalls";
import { splitFunnel, type CompanyOpens } from "@/lib/playbook-home";
import { THEME_TOKENS } from "@/lib/theme/tokens";
import { cn } from "@/lib/utils";

export type PlaybookHomeViewProps = {
  types: HomeType[];
  areas: CompanyAreaState[];
  canEdit: boolean;
  onCreateFunnel: () => void;
  onOpenType: (key: string) => void;
  onCreateCompany: () => void;
  onOpenCompany: (opens: CompanyOpens) => void;
  onCreateOther: () => void;
};

/**
 * The Playbook page in one screen, on the page's own background: the sales funnel and the company side by side, and under
 * them the calls outside the funnel. Everything is created and edited in windows that open over it.
 */
export function PlaybookHomeView(props: PlaybookHomeViewProps) {
  const { funnel, other } = splitFunnel(props.types);
  return (
    <div className={cn("space-y-14 py-4", THEME_TOKENS.motion.fadeIn)}>
      <div className="grid gap-14 lg:grid-cols-2 lg:gap-10">
        <FunnelBlock types={funnel} canEdit={props.canEdit} onCreate={props.onCreateFunnel} onEdit={props.onCreateFunnel} onOpen={props.onOpenType} />
        <CompanyBlock areas={props.areas} canEdit={props.canEdit} onCreate={props.onCreateCompany} onOpen={props.onOpenCompany} />
      </div>
      <OtherCalls types={other} canEdit={props.canEdit} onCreate={props.onCreateOther} onOpen={props.onOpenType} />
    </div>
  );
}
