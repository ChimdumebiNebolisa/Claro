import { useActorRef } from "@xstate/react";
import type { ReactNode } from "react";
import { WorkspaceActorContext } from "./workspaceActorContext";
import { workspaceMachine } from "./workspaceMachine";

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const actor = useActorRef(workspaceMachine);
  return (
    <WorkspaceActorContext.Provider value={actor}>
      {children}
    </WorkspaceActorContext.Provider>
  );
}
