import type { SubEngine } from './sub-engine.js';
import {
  ReturnCode,
  type Parameter,
  type RegisteredComponent,
  type CommandRequest,
  type QueryRequest,
  type SubscribeRequest,
  type EventSink,
} from './types.js';

/**
 * Router: the main HRI Engine router.
 *
 * Receives JSON-RPC method names from clients and dispatches them to the
 * appropriate SubEngine. Implements the four RoIS interfaces: System,
 * Command, Query, Event.
 *
 * Multi-sub-engine support:
 * - Holds a registry of SubEngine instances keyed by engine_id.
 * - Each sub-engine registers its components. search() and get_profile()
 *   aggregate across all sub-engines.
 * - execute, query, subscribe route to the sub-engine that owns the
 *   component ref.
 *
 * Multi-operator resource allocation:
 * - bind/release: tracks which operator has reserved which component.
 *   Only the bound operator can execute() on bind_required components.
 */
export class Router {
  // engine_id -> sub-engine entry
  private subEngines = new Map<
    string,
    { engineId: string; components: RegisteredComponent[]; subEngine: SubEngine }
  >();
  // bare component ref -> engine_id that owns it
  private componentIndex = new Map<string, string>();
  // full component ref (engineId/ref) -> operator id
  private bindings = new Map<string, string>();

  /**
   * Register a sub-engine and its components.
   * Called when an adapter sends rois.adapter.register.
   */
  registerSubEngine(
    engineId: string,
    components: RegisteredComponent[],
    subEngine: SubEngine,
  ): void {
    this.subEngines.set(engineId, { engineId, components, subEngine });
    this.rebuildIndex();
  }

  /** Remove a sub-engine (when its WebSocket disconnects). */
  unregisterSubEngine(engineId: string): void {
    this.subEngines.delete(engineId);
    this.rebuildIndex();
    // Release all bindings for this sub-engine's components.
    for (const ref of this.bindings.keys()) {
      if (ref.startsWith(`${engineId}/`)) {
        this.bindings.delete(ref);
      }
    }
  }

  /** Release all components bound by an operator. */
  releaseAll(operatorId: string): void {
    for (const [ref, owner] of this.bindings) {
      if (owner === operatorId) {
        this.bindings.delete(ref);
      }
    }
  }

  /** Get all registered sub-engine entries. */
  getSubEngines(): Array<{
    engineId: string;
    components: RegisteredComponent[];
    subEngine: SubEngine;
  }> {
    return [...this.subEngines.values()];
  }

  /** Get all registered components across all sub-engines. */
  getComponents(): Array<{ engineId: string; component: RegisteredComponent }> {
    const result: Array<{ engineId: string; component: RegisteredComponent }> = [];
    for (const entry of this.subEngines.values()) {
      for (const c of entry.components) {
        result.push({ engineId: entry.engineId, component: c });
      }
    }
    return result;
  }

  /** Get the current bindings. */
  getBindings(): Array<{ componentRef: string; operatorId: string }> {
    return [...this.bindings.entries()].map(([componentRef, operatorId]) => ({
      componentRef,
      operatorId,
    }));
  }

  /**
   * Dispatch a JSON-RPC method to the appropriate SubEngine.
   *
   * Returns a result object to be sent as the JSON-RPC response.
   * If the method is not supported, returns UNSUPPORTED.
   *
   * @param operatorId The sender identity, used for bind/release enforcement.
   * Null if the sender cannot be determined.
   */
  async dispatch(
    method: string,
    params: Record<string, unknown>,
    sink?: EventSink,
    operatorId?: string | null,
  ): Promise<Record<string, unknown>> {
    switch (method) {
      case 'rois.system.connect':
        return { return_code: ReturnCode.OK };
      case 'rois.system.disconnect':
        this.releaseAll(operatorId ?? '');
        return { return_code: ReturnCode.OK };
      case 'rois.system.get_profile':
        return this.handleGetProfile();
      case 'rois.command.search':
        return this.handleSearch();
      case 'rois.command.bind':
        return this.handleBind(params, operatorId ?? null);
      case 'rois.command.release':
        return this.handleRelease(params, operatorId ?? null);
      case 'rois.command.execute':
        return this.handleExecute(params, operatorId ?? null);
      case 'rois.query.query':
        return this.handleQuery(params);
      case 'rois.event.subscribe':
        return this.handleSubscribe(params, sink);
      case 'rois.event.unsubscribe':
        return this.handleUnsubscribe(params);
      default:
        return { return_code: ReturnCode.UNSUPPORTED };
    }
  }

  // ─── Handlers ─────────────────────────────────────────────────

  private async handleSearch(): Promise<Record<string, unknown>> {
    const refs: string[] = [];
    for (const entry of this.subEngines.values()) {
      for (const c of entry.components) {
        refs.push(`${entry.engineId}/${c.ref}`);
      }
    }
    return {
      return_code: ReturnCode.OK,
      component_ref_list: refs,
    };
  }

  private async handleGetProfile(): Promise<Record<string, unknown>> {
    const componentIds: string[] = [];
    const componentProfiles: Record<string, unknown>[] = [];

    for (const entry of this.subEngines.values()) {
      for (const c of entry.components) {
        const fullRef = `${entry.engineId}/${c.ref}`;
        componentIds.push(fullRef);
        componentProfiles.push({
          identifier: {
            authority: 'OpenRoIS',
            code: c.ref,
            codebook_ref: '',
            version: '',
          },
          name: c.ref,
          command_profiles: c.commands.map((name) => ({ name, results: [] })),
          query_profiles: c.queries.map((name) => ({ name, results: [] })),
          event_profiles: c.events.map((name) => ({ name, results: [] })),
        });
      }
    }

    return {
      return_code: ReturnCode.OK,
      profile: {
        identifier: {
          authority: 'OpenRoIS',
          code: 'Router',
          codebook_ref: '',
          version: '',
        },
        sub_engine_ids: [...this.subEngines.keys()],
        component_ids: componentIds,
        component_profiles: componentProfiles,
      },
    };
  }

  private async handleBind(
    params: Record<string, unknown>,
    operatorId: string | null,
  ): Promise<Record<string, unknown>> {
    const componentRef = String(params.component_ref ?? '');
    const component = this.findComponent(componentRef);
    if (!component) {
      return { return_code: ReturnCode.UNSUPPORTED };
    }
    if (!component.bindRequired) {
      return { return_code: ReturnCode.OK };
    }
    const currentOwner = this.bindings.get(componentRef);
    if (currentOwner && currentOwner !== operatorId) {
      return { return_code: ReturnCode.OUT_OF_RESOURCES };
    }
    this.bindings.set(componentRef, operatorId ?? '');
    return { return_code: ReturnCode.OK };
  }

  private async handleRelease(
    params: Record<string, unknown>,
    operatorId: string | null,
  ): Promise<Record<string, unknown>> {
    const componentRef = String(params.component_ref ?? '');
    if (this.bindings.get(componentRef) === operatorId) {
      this.bindings.delete(componentRef);
    }
    return { return_code: ReturnCode.OK };
  }

  private async handleExecute(
    params: Record<string, unknown>,
    operatorId: string | null,
  ): Promise<Record<string, unknown>> {
    const componentRef = String(params.component_ref ?? '');
    const component = this.findComponent(componentRef);
    if (!component) {
      return { return_code: ReturnCode.UNSUPPORTED };
    }
    if (component.bindRequired) {
      if (this.bindings.get(componentRef) !== operatorId) {
        return { return_code: ReturnCode.OUT_OF_RESOURCES };
      }
    }
    const subEngine = this.findSubEngine(componentRef);
    if (!subEngine) {
      return { return_code: ReturnCode.UNSUPPORTED };
    }
    // Support both spec structured format (command_unit_list) and
    // legacy flat format (command_type + parameters).
    const unitList = Array.isArray(params.command_unit_list)
      ? params.command_unit_list
      : [];
    const unit = (unitList[0] ?? {}) as Record<string, unknown>;
    const request: CommandRequest = {
      componentRef: String(unit.component_ref ?? params.component_ref ?? ''),
      commandType: String(unit.command_type ?? params.command_type ?? 'execute'),
      commandId: String(unit.command_id ?? ''),
      parameters: this.parseParameters(unit.arguments ?? params.parameters),
    };
    const response = await subEngine.invoke(request);
    return {
      return_code: response.returnCode,
      command_id: response.commandId,
    };
  }

  private async handleQuery(
    params: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const componentRef = String(params.component_ref ?? '');
    const subEngine = this.findSubEngine(componentRef);
    if (!subEngine) {
      return { return_code: ReturnCode.UNSUPPORTED };
    }
    const request: QueryRequest = {
      componentRef,
      queryType: String(params.query_type ?? ''),
      condition: String(params.condition ?? ''),
    };
    const response = await subEngine.query(request);
    return {
      return_code: response.returnCode,
      results: response.results,
    };
  }

  private async handleSubscribe(
    params: Record<string, unknown>,
    sink?: EventSink,
  ): Promise<Record<string, unknown>> {
    const componentRef = String(params.component_ref ?? '');
    const subEngine = this.findSubEngine(componentRef);
    if (!subEngine) {
      return { return_code: ReturnCode.UNSUPPORTED };
    }
    if (!sink) {
      return { return_code: ReturnCode.ERROR };
    }
    const request: SubscribeRequest = {
      componentRef,
      eventType: String(params.event_type ?? ''),
      condition: String(params.condition ?? ''),
    };
    const response = await subEngine.subscribe(request, sink);
    return {
      return_code: response.returnCode,
      subscribe_id: response.subscribeId,
    };
  }

  private async handleUnsubscribe(
    params: Record<string, unknown>,
  ): Promise<Record<string, unknown>> {
    const subscribeId = String(params.subscribe_id ?? '');
    // Unsubscribe from all sub-engines (we do not track which sub-engine
    // owns the subscription). In practice, the subscribe_id is unique
    // across sub-engines because each sub-engine generates its own IDs.
    for (const entry of this.subEngines.values()) {
      await entry.subEngine.unsubscribe(subscribeId);
    }
    return { return_code: ReturnCode.OK };
  }

  // ─── Helpers ──────────────────────────────────────────────────

  private rebuildIndex(): void {
    this.componentIndex.clear();
    for (const entry of this.subEngines.values()) {
      for (const c of entry.components) {
        this.componentIndex.set(c.ref, entry.engineId);
      }
    }
  }

  /**
   * Find a registered component by ref.
   * Strips the engine_id prefix if present (e.g., "pao/Navigation" -> "Navigation").
   */
  private findComponent(ref: string): RegisteredComponent | undefined {
    const bare = ref.includes('/') ? ref.slice(ref.indexOf('/') + 1) : ref;
    for (const entry of this.subEngines.values()) {
      const found = entry.components.find((c) => c.ref === bare);
      if (found) return found;
    }
    return undefined;
  }

  /**
   * Find the SubEngine that owns a component ref.
   * Strips the engine_id prefix and looks up the component index.
   */
  private findSubEngine(ref: string): SubEngine | undefined {
    const bare = ref.includes('/') ? ref.slice(ref.indexOf('/') + 1) : ref;
    const engineId = this.componentIndex.get(bare);
    if (!engineId) return undefined;
    return this.subEngines.get(engineId)?.subEngine;
  }

  private parseParameters(raw: unknown): Parameter[] {
    if (!Array.isArray(raw)) return [];
    return raw
      .filter(
        (item): item is Record<string, unknown> =>
          typeof item === 'object' && item !== null,
      )
      .map((item) => ({
        name: String(item.name ?? ''),
        dataTypeRef: String(item.data_type_ref ?? ''),
        value: String(item.value ?? ''),
      }));
  }
}
