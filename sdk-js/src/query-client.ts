/**
 * QueryClient: RoIS Query interface client for the OpenRoIS TypeScript SDK.
 *
 * Implements the QueryIF operation defined in the RoIS Framework 2.0
 * specification (RoIS_HRI::QueryApplicationBase):
 *
 *   query(componentRef, queryType, condition) -> rois.query.query
 *
 * Queries are synchronous: they return immediately with the requested data,
 * unlike commands which run asynchronously. Common query types include:
 *   "component_status" - returns the current ComponentStatus
 *   "robot_position"   - returns position data (SystemInformation)
 *   "engine_status"    - returns engine status (SystemInformation)
 *
 * Wire contract (docs/white-paper.md §8.2):
 *   rois.query.query {component_ref, query_type, condition} -> {return_code, results: Result[]}
 *
 * Architecture: docs/architecture.md section 4 (Client SDK layer)
 */

// 3. Internal packages (@openrois/*)
import {
  ReturnCodeSchema,
  ResultSchema,
  QueryResponseSchema,
} from "@openrois/interfaces";

import type {
  ReturnCode,
  Result,
} from "@openrois/interfaces";

// 4. Local modules
import { type WebSocketTransport } from "./transport";
import { RoISError } from "./engine";

// ---------------------------------------------------------------------------
// QueryClient
// ---------------------------------------------------------------------------

/**
 * Client for the RoIS Query interface.
 *
 * Wraps a connected {@link WebSocketTransport} and provides a typed, validated
 * method for synchronous queries. The transport must already be connected
 * before constructing or using a QueryClient.
 *
 * Usage:
 *   const engine = await RoISEngine.connect("wss://gateway.example.com");
 *   const query = new QueryClient(engine.getTransport);
 *
 *   // Query robot position from SystemInformation.
 *   const results = await query.query("SystemInformation_0", "robot_position");
 *   console.log(results[0].value);
 *
 *   // Query component status.
 *   const status = await query.query("PersonDetection_0", "component_status");
 *
 * Errors:
 *   - RoISError: the gateway returned a non-OK return_code.
 *   - RpcError: the gateway returned a JSON-RPC level error.
 *   - TransportError: the connection is not open.
 */
export class QueryClient {
  /** The underlying transport (must be connected). */
  private readonly transport: WebSocketTransport;

  /**
   * Create a QueryClient over an existing transport.
   *
   * @param transport - A connected WebSocketTransport instance.
   */
  constructor(transport: WebSocketTransport) {
    this.transport = transport;
  }

  // -----------------------------------------------------------------------
  // QueryIF operations
  // -----------------------------------------------------------------------

  /**
   * Run a synchronous query on a component.
   *
   * Queries return immediately with the requested data (unlike commands,
   * which run asynchronously). Common query types include:
   *   "component_status" - returns the current ComponentStatus
   *   "robot_position"   - returns position data (SystemInformation)
   *   "engine_status"    - returns engine status (SystemInformation)
   *
   * Maps to: rois.query.query
   * Request:  { component_ref: string, query_type: string, condition: string }
   * Response: { return_code, results: Result[] }
   *
   * @param componentRef - The component_ref to query.
   * @param queryType    - The query operation name (e.g. "robot_position").
   * @param condition    - Optional ISO 19143 filter expression. Defaults to "".
   * @returns The query results as an array of Result objects.
   *
   * @throws RoISError      if the gateway returns a non-OK return_code
   *                         (e.g. UNSUPPORTED for an unknown query type).
   * @throws TransportError if the connection is not open.
   */
  async query(
    componentRef: string,
    queryType: string,
    condition: string = "",
  ): Promise<Result[]> {
    const result = await this.transport.send("rois.query.query", {
      component_ref: componentRef,
      query_type: queryType,
      condition,
    });

    const parsed = QueryResponseSchema.parse(result);
    this.checkReturnCode(parsed.return_code, "rois.query.query");

    return parsed.results ?? [];
  }

  // -----------------------------------------------------------------------
  // Private: helpers
  // -----------------------------------------------------------------------

  /**
   * Check a ReturnCode and throw a RoISError if it is not OK.
   *
   * Mirrors the pattern in RoISEngine.checkReturnCode().
   */
  private checkReturnCode(returnCode: ReturnCode, method: string): void {
    if (returnCode !== "OK") {
      throw new RoISError(returnCode, method);
    }
  }
}