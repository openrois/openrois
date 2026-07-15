/**
 * CommandClient: RoIS Command interface client for the OpenRoIS TypeScript SDK.
 *
 * Implements the full CommandIF surface defined in the RoIS Framework 2.0
 * specification (RoIS_HRI::CommandApplicationBase):
 *
 *   search(condition)                 -> rois.command.search
 *   bind(componentRef)                -> rois.command.bind
 *   bindAny(condition)                -> rois.command.bind_any
 *   release(componentRef)             -> rois.command.release
 *   getParameter(componentRef, names) -> rois.command.get_parameter
 *   setParameter(componentRef, parameters) -> rois.command.set_parameter
 *   execute(componentRef, params)     -> rois.command.execute
 *   getCommandResult(commandId)       -> rois.command.get_command_result
 *
 * The bind/execute/release pattern is the standard way to interact with
 * components. After binding, you can set/get parameters and execute commands.
 * Call release() when done to free the component for other applications.
 *
 * Wire contract (docs/white-paper.md §8.2):
 *   rois.command.search             {condition}            -> {return_code, component_ref_list}
 *   rois.command.bind               {component_ref}        -> {return_code}
 *   rois.command.bind_any           {condition}            -> {return_code, component_ref}
 *   rois.command.release            {component_ref}        -> {return_code}
 *   rois.command.get_parameter      {component_ref, names} -> {return_code, results: Result[]}
 *   rois.command.set_parameter      {component_ref, parameters} -> {return_code, command_id}
 *   rois.command.execute            {component_ref, ...params}  -> {return_code, command_id, results?}
 *   rois.command.get_command_result  {command_id}                -> {return_code, results: Result[]}
 *
 * Architecture: docs/architecture.md section 4 (Client SDK layer)
 */

// 3. Internal packages (@openrois/*)
import {
  ReturnCodeSchema,
  ResultSchema,
  ParameterSchema,
  DiscoverResponseSchema,
  InvokeResponseSchema,
} from "@openrois/interfaces";

import type {
  ReturnCode,
  Result,
  Parameter,
  InvokeResponse,
} from "@openrois/interfaces";

// 4. Local modules
import { type WebSocketTransport } from "./transport";
import { RoISError } from "./rois-client";

// ---------------------------------------------------------------------------
// Response helpers (lightweight inline schemas)
// ---------------------------------------------------------------------------

/**
 * Response shape for rois.command.bind and rois.command.release.
 *
 *   { return_code }
 */
interface ReturnCodeResponse {
  return_code: ReturnCode;
}

/**
 * Response shape for rois.command.get_parameter.
 *
 *   { return_code, results: Result[] }
 */
interface GetParameterResponse {
  return_code: ReturnCode;
  results?: Result[];
}

/**
 * Response shape for rois.command.bind_any.
 *
 *   { return_code, component_ref }
 */
interface BindAnyResponse {
  return_code: ReturnCode;
  component_ref?: string;
}

/**
 * Response shape for rois.command.get_command_result.
 *
 *   { return_code, results: Result[] }
 */
interface GetCommandResultResponse {
  return_code: ReturnCode;
  results?: Result[];
}

// ---------------------------------------------------------------------------
// CommandClient
// ---------------------------------------------------------------------------

/**
 * Client for the RoIS Command interface operations.
 *
 * Wraps a connected {@link WebSocketTransport} and provides typed, validated
 * methods for the bind/execute/release lifecycle and parameter management.
 * The transport must already be connected before constructing or using a
 * CommandClient.
 *
 * Usage:
 *   const client = await RoISClient.connect("wss://gateway.example.com");
 *   const command = new CommandClient(engine.transport);
 *
 *   // Search for available components.
 *   const refs = await command.search();
 *
 *   // Bind a component for exclusive use.
 *   await command.bind("Navigation_0");
 *
 *   // Configure parameters before executing.
 *   await command.setParameter("Navigation_0", [
 *     { name: "target_positions", data_type_ref: "string[]", value: '["3.0,1.5,0.0"]' },
 *     { name: "time_limit", data_type_ref: "int", value: "30" },
 *   ]);
 *
 *   // Read current parameter values.
 *   const params = await command.getParameter("Navigation_0", ["target_positions"]);
 *
 *   // Release when done.
 *   await command.release("Navigation_0");
 *
 * Errors:
 *   - RoISError: the gateway returned a non-OK return_code.
 *   - RpcError: the gateway returned a JSON-RPC level error.
 *   - TransportError: the connection is not open.
 */
export class CommandClient {
  /** The underlying transport (must be connected). */
  private readonly transport: WebSocketTransport;

  /**
   * Create a CommandClient over an existing transport.
   *
   * @param transport - A connected WebSocketTransport instance.
   */
  constructor(transport: WebSocketTransport) {
    this.transport = transport;
  }

  // -----------------------------------------------------------------------
  // CommandIF: discovery and lifecycle
  // -----------------------------------------------------------------------

  /**
   * Search for components matching a condition.
   *
   * Returns a list of component_ref identifiers that can be passed to
   * bind(), getParameter(), setParameter(), or query().
   *
   * Maps to: rois.command.search
   * Request:  { condition: string }
   * Response: { return_code, component_ref_list: string[] }
   *
   * @param condition - ISO 19143 filter expression. Empty string returns all
   *                     available components. Defaults to "".
   * @returns List of matching component_ref identifiers.
   *
   * @throws RoISError      if the gateway returns a non-OK return_code.
   * @throws TransportError if the connection is not open.
   */
  async search(condition: string = ""): Promise<string[]> {
    const result = await this.transport.send("rois.command.search", {
      condition,
    });

    const parsed = DiscoverResponseSchema.parse(result);
    this.checkReturnCode(parsed.return_code, "rois.command.search");

    return parsed.component_ref_list ?? [];
  }

  /**
   * Reserve a specific component for exclusive use.
   *
   * The bind/execute/release pattern is the standard way to interact with
   * components. After binding, you can set/get parameters, execute commands,
   * and receive events from the component. Call release() when done.
   *
   * Maps to: rois.command.bind
   * Request:  { component_ref: string }
   * Response: { return_code }
   *
   * @param componentRef - The component_ref from search() results.
   * @returns The ReturnCode from the gateway (OK on success).
   *
   * @throws RoISError      if the gateway returns a non-OK return_code
   *                         (e.g. UNSUPPORTED for an unknown component).
   * @throws TransportError if the connection is not open.
   */
  async bind(componentRef: string): Promise<ReturnCode> {
    const result = await this.transport.send("rois.command.bind", {
      component_ref: componentRef,
    });

    const parsed = result as ReturnCodeResponse;
    const returnCode = ReturnCodeSchema.parse(parsed.return_code);
    this.checkReturnCode(returnCode, "rois.command.bind");

    return returnCode;
  }

  /**
   * Release a previously bound component.
   *
   * Frees the component for other applications. Any active subscriptions
   * or in-progress commands on this component should be cleaned up first.
   *
   * Maps to: rois.command.release
   * Request:  { component_ref: string }
   * Response: { return_code }
   *
   * @param componentRef - The component_ref to release.
   * @returns The ReturnCode from the gateway (OK on success).
   *
   * @throws RoISError      if the gateway returns a non-OK return_code.
   * @throws TransportError if the connection is not open.
   */
  async release(componentRef: string): Promise<ReturnCode> {
    const result = await this.transport.send("rois.command.release", {
      component_ref: componentRef,
    });

    const parsed = result as ReturnCodeResponse;
    const returnCode = ReturnCodeSchema.parse(parsed.return_code);
    this.checkReturnCode(returnCode, "rois.command.release");

    return returnCode;
  }

  // -----------------------------------------------------------------------
  // CommandIF: parameter management
  // -----------------------------------------------------------------------

  /**
   * Get current parameter values for a bound component.
   *
   * If `names` is provided, only the requested parameters are returned.
   * If `names` is omitted or empty, all parameters for the component are
   * returned.
   *
   * Maps to: rois.command.get_parameter
   * Request:  { component_ref: string, names?: string[] }
   * Response: { return_code, results: Result[] }
   *
   * @param componentRef - The component_ref to query.
   * @param names        - Optional list of parameter names to fetch. If empty
   *                       or omitted, all parameters are returned.
   * @returns The parameter values as an array of Result objects.
   *
   * @throws RoISError      if the gateway returns a non-OK return_code.
   * @throws TransportError if the connection is not open.
   */
  async getParameter(componentRef: string, names: string[] = []): Promise<Result[]> {
    const result = await this.transport.send("rois.command.get_parameter", {
      component_ref: componentRef,
      ...(names.length > 0 ? { names } : {}),
    });

    const parsed = result as GetParameterResponse;
    const returnCode = ReturnCodeSchema.parse(parsed.return_code);
    this.checkReturnCode(returnCode, "rois.command.get_parameter");

    return ResultSchema.array().parse(parsed.results ?? []);
  }

  /**
   * Set parameter values on a bound component.
   *
   * For example, setting navigation targets:
   *   await command.setParameter("Navigation_0", [
   *     { name: "target_positions", data_type_ref: "string[]", value: '["3.0,1.5,0.0"]' },
   *     { name: "time_limit", data_type_ref: "int", value: "30" },
   *   ]);
   *
   * Maps to: rois.command.set_parameter
   * Request:  { component_ref: string, parameters: Parameter[] }
   * Response: { return_code, command_id }
   *
   * @param componentRef - The component_ref to configure.
   * @param parameters   - Named parameters to set, each with name,
   *                        data_type_ref, and value.
   * @returns The InvokeResponse with return_code and command_id.
   *
   * @throws RoISError      if the gateway returns a non-OK return_code.
   * @throws TransportError if the connection is not open.
   */
  async setParameter(
    componentRef: string,
    parameters: Parameter[],
  ): Promise<InvokeResponse> {
    // Validate each parameter with the canonical schema before sending.
    const validated = ParameterSchema.array().parse(parameters);

    const result = await this.transport.send("rois.command.set_parameter", {
      component_ref: componentRef,
      parameters: validated,
    });

    const parsed = InvokeResponseSchema.parse(result);
    this.checkReturnCode(parsed.return_code, "rois.command.set_parameter");

    return parsed;
  }

  /**
   * Reserve any component matching a condition.
   *
   * Like {@link bind}, but the gateway picks the best available component
   * instead of the caller specifying one. Useful when multiple components
   * can serve the same purpose (e.g. any available camera).
   *
   * Maps to: rois.command.bind_any
   * Request:  { condition: string }
   * Response: { return_code, component_ref: string }
   *
   * @param condition - ISO 19143 filter expression to match candidate
   *                     components. Empty string matches any available.
   * @returns The component_ref of the bound component.
   *
   * @throws RoISError      if the gateway returns a non-OK return_code
   *                         (e.g. OUT_OF_RESOURCES if none available).
   * @throws TransportError if the connection is not open.
   */
  async bindAny(condition: string = ""): Promise<string> {
    const result = await this.transport.send("rois.command.bind_any", {
      condition,
    });

    const parsed = result as BindAnyResponse;
    const returnCode = ReturnCodeSchema.parse(parsed.return_code);
    this.checkReturnCode(returnCode, "rois.command.bind_any");

    return parsed.component_ref ?? "";
  }

  /**
   * Execute a command on a bound component.
   *
   * Commands run asynchronously. This method returns immediately with a
   * command_id. Listen for "rois.command.completed" events to know when
   * the command finishes:
   *
   *   const cmdId = await command.execute("Navigation_0", {
   *     target_positions: ["3.0,1.5,0.0"],
   *     time_limit: 30,
   *   });
   *   engine.on("rois.command.completed", (notification) => {
   *     if (notification.params.command_id === cmdId) {
   *       console.log("Navigation complete:", notification.params.status);
   *     }
   *   });
   *
   * Maps to: rois.command.execute
   * Request:  { component_ref: string, ...params }
   * Response: { return_code, command_id, results? }
   *
   * @param componentRef - The component_ref to command.
   * @param params       - Command parameters (component-specific). These are
   *                        spread into the request alongside component_ref.
   * @returns The InvokeResponse with return_code and command_id.
   *
   * @throws RoISError      if the gateway returns a non-OK return_code.
   * @throws TransportError if the connection is not open.
   */
  async execute(
    componentRef: string,
    params: Record<string, unknown>,
  ): Promise<InvokeResponse> {
    const result = await this.transport.send("rois.command.execute", {
      component_ref: componentRef,
      ...params,
    });

    const parsed = InvokeResponseSchema.parse(result);
    this.checkReturnCode(parsed.return_code, "rois.command.execute");

    return parsed;
  }

  /**
   * Get the result of a completed command.
   *
   * Call this after receiving a "rois.command.completed" notification
   * for the given command_id.
   *
   * Maps to: rois.command.get_command_result
   * Request:  { command_id: string }
   * Response: { return_code, results: Result[] }
   *
   * @param commandId - The command_id from execute() or a completed event.
   * @returns The command results as an array of Result objects.
   *
   * @throws RoISError      if the gateway returns a non-OK return_code.
   * @throws TransportError if the connection is not open.
   */
  async getCommandResult(commandId: string): Promise<Result[]> {
    const result = await this.transport.send("rois.command.get_command_result", {
      command_id: commandId,
    });

    const parsed = result as GetCommandResultResponse;
    const returnCode = ReturnCodeSchema.parse(parsed.return_code);
    this.checkReturnCode(returnCode, "rois.command.get_command_result");

    return ResultSchema.array().parse(parsed.results ?? []);
  }

  // -----------------------------------------------------------------------
  // Private: helpers
  // -----------------------------------------------------------------------

  /**
   * Check a ReturnCode and throw a RoISError if it is not OK.
   *
   * Mirrors the pattern in RoISClient.checkReturnCode().
   */
  private checkReturnCode(returnCode: ReturnCode, method: string): void {
    if (returnCode !== "OK") {
      throw new RoISError(returnCode, method);
    }
  }
}