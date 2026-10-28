// Prototype (prototypes/playbook-briefing/index.html), dev server only: the real Playbook page (SalesProcessPage) on the
// local read-only API, where a call type of the funnel opens the workspace (Workspace) instead of its playbook
// document, with Vocify's real playbooks, company notes and model.
import { PlaybookDetailContext } from "@/features/playbooks/detailOverride";
import SalesProcessPage from "@/pages/dashboard/SalesProcessPage";
import { boot } from "@/prototypes/shared/boot";
import { Workspace } from "./Workspace";

const openWorkspace = (key: string) => <Workspace key={key} motion={key} />;

function Prototype() {
  return (
    <PlaybookDetailContext.Provider value={openWorkspace}>
      <div className="dashboard-shell h-dvh w-full overflow-hidden bg-background">
        <main className="app-scroll h-full overflow-y-auto p-6 md:p-8">
          <SalesProcessPage />
        </main>
      </div>
    </PlaybookDetailContext.Provider>
  );
}

boot("/dashboard/sales-process", <Prototype />);
