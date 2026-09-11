import { useSelector } from "@xstate/react";
import { useContext } from "react";
import {
  WorkspaceActorContext,
  type WorkspaceActor,
  type WorkspaceSnapshot,
} from "./workspaceActorContext";

export function useWorkspaceActor(): WorkspaceActor {
  const actor = useContext(WorkspaceActorContext);
  if (!actor) {
    throw new Error("useWorkspaceActor must be used inside WorkspaceProvider");
  }
  return actor;
}

export function useWorkspaceSnapshot(): WorkspaceSnapshot {
  const actor = useWorkspaceActor();
  return useSelector(actor, (snapshot) => snapshot);
}
