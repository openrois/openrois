import type { RoISClient } from "@openrois/sdk";
import type { HRIComponentProfile } from "@openrois/interfaces";
import { ComponentPanel } from "./ComponentPanel";

interface EngineGroupProps {
  engineId: string;
  client: RoISClient | null;
  componentRefs: string[];
  componentProfiles: HRIComponentProfile[];
}

/**
 * Render all components belonging to one engine (adapter).
 *
 * Groups components by their engine_id prefix (e.g. "kachaka_01")
 * so the operator can see which adapter owns which capabilities.
 */
export function EngineGroup({
  engineId,
  client,
  componentRefs,
  componentProfiles,
}: EngineGroupProps) {
  return (
    <div className="engine-group">
      <div className="engine-group-header">
        <h3 className="engine-group-title">{engineId}</h3>
        <span className="engine-group-count">
          {componentRefs.length} component{componentRefs.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="component-grid">
        {componentRefs.map((ref, i) => (
          <ComponentPanel
            key={ref}
            client={client}
            componentRef={ref}
            profile={componentProfiles[i]}
          />
        ))}
      </div>
    </div>
  );
}