import type { ComponentContract } from './component-contract.js';
import {
  ReturnCode,
  type Parameter,
  type RegisteredComponent,
  type CommandRequest,
  type QueryRequest,
  type SubscribeRequest,
  type EventSink,
} from './types.js';

// ---------------------------------------------------------------------------
// Binding enforcement helper
// ---------------------------------------------------------------------------

const COMMAND_TYPES_REQUIRING_BIND = new Set(['start', 'stop', 'suspend', 'resume', 'execute']);

function requiresBind(fn: string | null, commands: string[]): boolean {
  if (fn !== 'actuation') return false;
  return commands.some((c) => COMMAND_TYPES_REQUIRING_BIND.has(c.toLowerCase()));
}

/**
 * Engine: the recursive HRI Engine.
 *
 * Manages HRI Components. Routes RoIS JSON-RPC calls to child engines
 * (sub-engines) based on component ref. Implements the five RoIS
 * interfaces: System, Command, Query, Event, Streaming.
 *
 * When hosted by the gateway: has child engines (SubEngine proxies),
 * no local components. Aggregates profiles from all child engines.
 *
 * When hosted by an adapter: has local components (ComponentRegistry),
 * no child engines. Registers with the parent engine over WebSocket.
 *
 * The design supports nesting (child engines with their own child
 * engines), but only the main engine and one level of sub-engines
 * are used today.
 *
 * Multi-client resource allocation:
 * - bind/release: tracks which client has reserved which component.
 *   Only the bound client can execute() on actuation components.
 */
export class Engine {
  // engine_id -> sub-engine entry
  private subEngines = new Map<
    string,
    { engineId: string; platform: string; components: RegisteredComponent[]; subEngine: ComponentContract }
  >();
  // bare component ref -> engine_id that owns it
  private componentIndex = new Map<string, string>();
  // full component ref (engineId/ref) -> client id
  private bindings = new Map<string, string>();
  // Whether to enforce bind/release on execute. Defaults to false
  // (adapter mode). The gateway sets this to true.
  private readonly enforceBindings: boolean;

  /**
   * Create an Engine.
   *
   * @param enforceBindings - Whether to enforce bind/release on
   *   execute. Defaults to false (adapter mode). The main HRI Engine
   *   (gateway) sets this to true: only the client that called bind()
   *   can call execute() on actuation components. Adapters leave it
   *   false: the gateway already authorized the command, so the
   *   adapter trusts it and skips the redundant check. Per the RoIS
   *   spec, resource ownership is consolidated in the HRI Engine.
   */
  constructor(enforceBindings: boolean = false) {
    this.enforceBindings = enforceBindings;
  }

  /**
   * Register a sub-engine and its components.
   * Called when an adapter sends rois.adapter.register.
   */
  registerSubEngine(
    engineId: string,
    components: RegisteredComponent[],
    subEngine: ComponentContract,
    platform: string = '',
  ): void {
    this.subEngines.set(engineId, { engineId, platform, components, subEngine });
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

  /** Release all components bound by a client. */
  releaseAll(clientId: string): void {
    for (const [ref, owner] of this.bindings) {
      if (owner === clientId) {
        this.bindings.delete(ref);
      }
    }
  }

  /** Get all registered sub-engine entries. */
  getSubEngines(): Array<{
    engineId: string;
    platform: string;
    components: RegisteredComponent[];
    subEngine: ComponentContract;
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
  getBindings(): Array<{ componentRef: string; clientId: string }> {
    return [...this.bindings.entries()].map(([componentRef, clientId]) => ({
      componentRef,
      clientId,
    }));
  }

  /**
   * Dispatch a JSON-RPC method to the appropriate child engine.
   *
   * Returns a result object to be sent as the JSON-RPC response.
   * If the method is not supported, returns UNSUPPORTED.
   *
   * @param clientId The sender identity, used for bind/release enforcement.
   * Null if the sender cannot be determined.
   */
  async dispatch(
    method: string,
    params: Record<string, unknown>,
    sink?: EventSink,
    clientId?: string | null,
  ): Promise<Record<string, unknown>> {
    switch (method) {
      case 'rois.system.connect':
        return { return_code: ReturnCode.OK };
      case 'rois.system.disconnect':
        this.releaseAll(clientId ?? '');
        return { return_code: ReturnCode.OK };
      case 'rois.system.get_profile':
        return this.handleGetProfile();
      case 'rois.command.search':
        return this.handleSearch();
      case 'rois.command.bind':
        return this.handleBind(params, clientId ?? null);
      case 'rois.command.release':
        return this.handleRelease(params, clientId ?? null);
      case 'rois.command.execute':
        return this.handleExecute(params, clientId ?? null);
      case 'rois.command.set_parameter':
        return this.handleSetParameter(params, clientId ?? null);
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
          function: c.function,
          command_profiles: c.commands.map((name) => ({ name, results: [] })),
          query_profiles: c.queries.map((name) => ({ name, results: [] })),
          event_profiles: c.events.map((name) => ({ name, results: [] })),
          parameter_profiles: c.parameters,
        });
      }
    }

    return {
      return_code: ReturnCode.OK,
      profile: {
        identifier: {
          authority: 'OpenRoIS',
          code: 'Engine',
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
    clientId: string | null,
  ): Promise<Record<string, unknown>> {
    const componentRef = String(params.component_ref ?? '');
    const component = this.findComponent(componentRef);
    if (!component) {
      return { return_code: ReturnCode.UNSUPPORTED };
    }
    if (!requiresBind(component.function, component.commands)) {
      return { return_code: ReturnCode.OK };
    }
    const currentOwner = this.bindings.get(componentRef);
    if (currentOwner && currentOwner !== clientId) {
      return { return_code: ReturnCode.OUT_OF_RESOURCES };
    }
    this.bindings.set(componentRef, clientId ?? '');
    return { return_code: ReturnCode.OK };
  }

  private async handleRelease(
    params: Record<string, unknown>,
    clientId: string | null,
  ): Promise<Record<string, unknown>> {
    const componentRef = String(params.component_ref ?? '');
    if (this.bindings.get(componentRef) === (clientId ?? '')) {
      this.bindings.delete(componentRef);
    }
    return { return_code: ReturnCode.OK };
  }

  private async handleExecute(
    params: Record<string, unknown>,
    clientId: string | null,
  ): Promise<Record<string, unknown>> {
    const componentRef = String(params.component_ref ?? '');
    const component = this.findComponent(componentRef);
    if (!component) {
      return { return_code: ReturnCode.UNSUPPORTED };
    }
    if (requiresBind(component.function, component.commands)) {
      if (this.enforceBindings) {
        if (this.bindings.get(componentRef) !== (clientId ?? '')) {
          return { return_code: ReturnCode.OUT_OF_RESOURCES };
        }
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

  private async handleSetParameter(
    params: Record<string, unknown>,
    clientId: string | null,
  ): Promise<Record<string, unknown>> {
    const componentRef = String(params.component_ref ?? '');
    const component = this.findComponent(componentRef);
    if (!component) {
      return { return_code: ReturnCode.UNSUPPORTED };
    }
    const subEngine = this.findSubEngine(componentRef);
    if (!subEngine) {
      return { return_code: ReturnCode.UNSUPPORTED };
    }
    const request: CommandRequest = {
      componentRef,
      commandType: 'set_parameter',
      commandId: '',
      parameters: this.parseParameters(params.parameters),
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
   * If the ref includes an engine_id prefix (e.g. "kachaka_01/Navigation"),
   * look up that specific sub-engine only. If the engine is not registered,
   * return undefined (UNSUPPORTED). Do not fall back to other engines.
   * For bare refs (no prefix), search all sub-engines.
   */
  private findComponent(ref: string): RegisteredComponent | undefined {
    if (ref.includes('/')) {
      const slashIdx = ref.indexOf('/');
      const engineId = ref.slice(0, slashIdx);
      const bare = ref.slice(slashIdx + 1);
      const entry = this.subEngines.get(engineId);
      if (entry) {
        return entry.components.find((c) => c.ref === bare);
      }
      return undefined;
    }
    for (const entry of this.subEngines.values()) {
      const found = entry.components.find((c) => c.ref === ref);
      if (found) return found;
    }
    return undefined;
  }

  /**
   * Find the SubEngine that owns a component ref.
   * If the ref includes an engine_id prefix (e.g. "kachaka_01/Navigation"),
   * route to that specific sub-engine only. If the engine is not registered,
   * return undefined (UNSUPPORTED). Do not fall back to other engines.
   * For bare refs (no prefix), use the component index.
   */
  private findSubEngine(ref: string): ComponentContract | undefined {
    if (ref.includes('/')) {
      const slashIdx = ref.indexOf('/');
      const engineId = ref.slice(0, slashIdx);
      const bare = ref.slice(slashIdx + 1);
      const entry = this.subEngines.get(engineId);
      if (entry && entry.components.some((c) => c.ref === bare)) {
        return entry.subEngine;
      }
      return undefined;
    }
    const engineId = this.componentIndex.get(ref);
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
