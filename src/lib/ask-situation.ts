export type AskCoverage = "complete" | "partial" | "forbidden" | "unavailable";

export type AskSituation = {
  message: string;
  action: "ask" | "retry" | "none";
};

export function askSituation(input: {
  hasTurns: boolean;
  coverage?: AskCoverage | null;
  items?: number;
}): AskSituation {
  if (!input.hasTurns) {
    return { message: "askEmpty", action: "ask" };
  }
  if (input.coverage === "forbidden") {
    return { message: "askForbidden", action: "retry" };
  }
  if (input.coverage === "partial") {
    return { message: "askPartial", action: "retry" };
  }
  if (input.coverage === "unavailable") {
    return { message: "askUnavailable", action: "retry" };
  }
  if (input.coverage === "complete" && (input.items ?? 0) === 0) {
    return { message: "askNoResults", action: "none" };
  }
  return { message: "", action: "none" };
}

export function askConfirmation(turn: {
  confirmation?: { operation_id?: string; revision?: number; contact_id?: string } | null;
}): { operationId: string; revision: number; contactId: string } | null {
  const confirmation = turn.confirmation;
  if (!confirmation?.operation_id || confirmation.revision == null || !confirmation.contact_id) {
    return null;
  }
  return {
    operationId: confirmation.operation_id,
    revision: confirmation.revision,
    contactId: confirmation.contact_id,
  };
}
