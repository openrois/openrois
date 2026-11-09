import { useMemo, useState, type KeyboardEvent } from "react";
import { useSession } from "../lib/useSession";
import { allComponents, engineTree, typeName, type EngineNode } from "../lib/engines";
import { Pill, Tag } from "./ui";
import type { View } from "../App";

function ComponentRow({
  componentRef,
  view,
  onOpen,
}: {
  componentRef: string;
  view: View;
  onOpen: (view: View) => void;
}) {
  const [, state] = useSession();
  const profile = state.profile?.component_profiles[componentRef];
  if (!profile) return null;
  const status = state.statuses[componentRef];
  const bound = state.bound.has(componentRef);
  const name = componentRef.slice(componentRef.indexOf("/") + 1);
  return (
    <button
      type="button"
      className="tree-component"
      data-tree-item
      aria-current={view.kind === "component" && view.ref === componentRef}
      onClick={() => onOpen({ kind: "component", ref: componentRef, tab: "overview" })}
      title={`${componentRef} · ${typeName(profile)}${profile.function ? ` · ${profile.function}` : ""}`}
    >
      <span
        className={`dot ${profile.function === "actuation" ? "actuation" : profile.function === "sensing" ? "sensing" : ""}`}
        aria-hidden
      />
      <span className="labels">
        <span className="name">{name}</span>
        <span className="row" style={{ gap: 4 }}>
          <Tag>{typeName(profile)}</Tag>
          {status && <Pill status={status} />}
        </span>
      </span>
      <span className="meta">{bound && <Pill status="RUNNING" label="Bound" />}</span>
    </button>
  );
}

function matches(ref: string, query: string, type: string): boolean {
  const q = query.trim().toLowerCase();
  return q === "" || ref.toLowerCase().includes(q) || type.toLowerCase().includes(q);
}

function EngineBranch({
  node,
  root,
  view,
  query,
  onOpen,
}: {
  node: EngineNode;
  root: boolean;
  view: View;
  query: string;
  onOpen: (view: View) => void;
}) {
  const [, state] = useSession();
  const profiles = state.profile?.component_profiles ?? {};
  const shown = node.components.filter((ref) => matches(ref, query, profiles[ref] ? typeName(profiles[ref]) : ""));
  return (
    <div className="tree-engine">
      <div className="tree-engine-head">
        <span>{node.id}</span>
        <span className="role kicker">{root ? "Main HRI Engine" : "Child Engine"}</span>
      </div>
      <div className="tree-children">
        {shown.map((ref) => (
          <ComponentRow key={ref} componentRef={ref} view={view} onOpen={onOpen} />
        ))}
        {node.children.map((child) => (
          <EngineBranch key={child.id} node={child} root={false} view={view} query={query} onOpen={onOpen} />
        ))}
        {node.components.length === 0 && node.children.length === 0 && (
          <div className="empty">No components yet.</div>
        )}
      </div>
    </div>
  );
}

/** Up and Down move between the rows of the tree, as in a file browser. */
function moveFocus(event: KeyboardEvent<HTMLElement>): void {
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  const items = [...event.currentTarget.querySelectorAll<HTMLElement>("[data-tree-item]")];
  const index = items.indexOf(document.activeElement as HTMLElement);
  const next = items[index + (event.key === "ArrowDown" ? 1 : -1)];
  if (next) {
    event.preventDefault();
    next.focus();
  }
}

export function Sidebar({ view, onOpen }: { view: View; onOpen: (view: View) => void }) {
  const [session, state] = useSession();
  const [query, setQuery] = useState("");
  const tree = useMemo(() => (state.profile ? engineTree(state.profile) : null), [state.profile]);
  const running = state.commands.filter((c) => c.status === "RUNNING").length;
  const engines = tree ? countEngines(tree) : 0;
  const components = tree ? allComponents(tree).length : 0;

  return (
    <nav className="sidebar" aria-label="Engines and components" onKeyDown={moveFocus}>
      <div className="nav">
        <button type="button" data-tree-item aria-current={view.kind === "welcome"} onClick={() => onOpen({ kind: "welcome" })}>
          Overview
        </button>
        <button
          type="button"
          data-tree-item
          aria-current={view.kind === "sequence"}
          onClick={() => onOpen({ kind: "sequence" })}
          disabled={!tree}
        >
          Command Sequence
          {running > 0 && <span className="count">{running} running</span>}
        </button>
      </div>

      <div className="section-label kicker">Engines</div>
      {tree && (
        <input
          className="input rail-search"
          type="search"
          placeholder="Filter by id or type"
          aria-label="Filter components"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      )}
      {tree ? (
        <EngineBranch node={tree} root view={view} query={query} onOpen={onOpen} />
      ) : (
        <div className="empty">Connect to a gateway to see its engines and components.</div>
      )}

      {tree && (
        <div className="rail-foot">
          <span>
            {engines} engines · {components} components · {state.bound.size} bound
          </span>
          <span>Everything here comes from the engine profile.</span>
          <span className="row" style={{ justifyContent: "space-between" }}>
            <span>
              <Tag>get_profile</Tag> {state.profileMs ?? "?"} ms
            </span>
            <button
              type="button"
              className="btn btn-ghost btn-small"
              onClick={() => void session.refreshProfile().catch((e) => session.note("rois.system.get_profile", String(e)))}
            >
              Refresh
            </button>
          </span>
        </div>
      )}
    </nav>
  );
}

function countEngines(node: EngineNode): number {
  return 1 + node.children.reduce((n, child) => n + countEngines(child), 0);
}
