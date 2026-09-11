import { createContext } from "react";
import type { ActorRefFrom, SnapshotFrom } from "xstate";
import { workspaceMachine } from "./workspaceMachine";

export type WorkspaceActor = ActorRefFrom<typeof workspaceMachine>;
export type WorkspaceSnapshot = SnapshotFrom<typeof workspaceMachine>;

export const WorkspaceActorContext = createContext<WorkspaceActor | null>(null);
