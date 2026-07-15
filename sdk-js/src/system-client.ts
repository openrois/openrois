/**
 * SystemClient: RoIS System interface client for the OpenRoIS TypeScript SDK.
 *
 * Implements the SystemIF operations defined in the RoIS Framework 2.0
 * specification (RoIS_Service::SystemApplicationBase):
 *
 *   getProfile(condition)  -> rois.system.get_profile
 *   getErrorDetail(errorId) -> rois.system.get_error_detail
 *
 * The connect/disconnect lifecycle methods remain on RoISEngine (engine.ts)
 * because they own the transport and connection state. SystemClient focuses on
 * the two query-style System operations that run over an established
 * connection.
 *
 * Wire contract (docs/white-paper.md §8.2):
 *   rois.system.get_profile      {condition: string}  -> {return_code, profile}
 *   rois.system.get_error_detail {error_id: string}   -> {return_code, results: Result[]}
 *
 * Architecture: docs/architecture.md section 4 (Client SDK layer)
 */

// 3. Internal packages (@openrois/*)
import {
  ReturnCodeSchema,
  ResultSchema,
  HRIEngineProfileTypeSchema,
} from "@openrois/interfaces";

import type {
  ReturnCode,
  Result,
  HRIEngineProfileType,
} from "@openrois/interfaces";

// 4. Local modules
import { type WebSocketTransport } from "./transport";
import { RoISError } from "./engine";

// ---------------------------------------------------------------------------
// Response helpers (lightweight inline schemas)
// ---------------------------------------------------------------------------

/**
 * Response shape for rois.system.get_profile.
 *
 *   { return_code, profile }
 *
 * The `profile` field carries an HRI_Engine_Profile. Per the IDL this is a
 * string (XML), but OpenRoIS gateways may return the structured
 * HRIEngineProfileType object directly over JSON-RPC. We validate it with
 * the canonical HRIEngineProfileTypeSchema.
 */
interface GetProfileResponse {
  return_code: ReturnCode;
  profile: unknown;
}

/**
 * Response shape for rois.system.get_error_detail.
 *
 *   { return_code, results: Result[] }
 *
 * Maps to the Error Detail Message (docs/rois-reference.md §8).
 */
interface GetErrorDetailResponse {
  return_code: ReturnCode;
  results?: Result[];
}

// ---------------------------------------------------------------------------
// SystemClient
// ---------------------------------------------------------------------------

/**
 * Client for the RoIS System interface query operations.
 *
 * Wraps a connected {@link WebSocketTransport} and provides typed, validated
 * methods for `get_profile` and `get_error_detail`. The transport must already
 * be connected before constructing or using a SystemClient.
 *
 * Usage:
 *   const engine = await RoISEngine.connect("wss://gateway.example.com");
 *   const system = new SystemClient(engine.transport);
 *
 *   const profile = await system.getProfile();
 *   console.log(profile.component_ids);
 *
 *   const details = await system.getErrorDetail("err-001");
 *   console.log(details);
 *
 * Errors:
 *   - RoISError: the gateway returned a non-OK return_code.
 *   - RpcError: the gateway returned a JSON-RPC level error.
 *   - TransportError: the connection is not open.
 */
export class SystemClient {
  /** The underlying transport (must be connected). */
  private readonly transport: WebSocketTransport;

  /**
   * Create a SystemClient over an existing transport.
   *
   * @param transport - A connected WebSocketTransport instance.
   */
  constructor(transport: WebSocketTransport) {
    this.transport = transport;
  }

  // -----------------------------------------------------------------------
  // SystemIF operations
  // -----------------------------------------------------------------------

  /**
   * Retrieve the gateway's HRI Engine profile.
   *
   * The profile describes all available components, their capabilities, and
   * supported operations. This is the aggregated profile from all
   * sub-engines behind the gateway.
   *
   * Maps to: rois.system.get_profile
   * Request:  { condition: string }
   * Response: { return_code, profile: HRIEngineProfileType }
   *
   * @param condition - ISO 19143 filter expression. Empty string returns the
   *                     full profile. Defaults to "".
   * @returns The validated HRI Engine profile.
   *
   * @throws RoISError      if the gateway returns a non-OK return_code.
   * @throws TransportError if the connection is not open.
   */
  async getProfile(condition: string = ""): Promise<HRIEngineProfileType> {
    const result = await this.transport.send("rois.system.get_profile", {
      condition,
    });

    const parsed = result as GetProfileResponse;
    const returnCode = ReturnCodeSchema.parse(parsed.return_code);
    this.checkReturnCode(returnCode, "rois.system.get_profile");

    return HRIEngineProfileTypeSchema.parse(parsed.profile);
  }

  /**
   * Get detailed information about a specific error.
   *
   * After receiving a `notify_error` notification, call this with the
   * `error_id` to retrieve human-readable details about what went wrong.
   *
   * Maps to: rois.system.get_error_detail
   * Request:  { error_id: string }
   * Response: { return_code, results: Result[] }
   *
   * @param errorId - The error identifier from a notify_error event.
   * @returns The error detail results as an array of Result objects.
   *
   * @throws RoISError      if the gateway returns a non-OK return_code.
   * @throws TransportError if the connection is not open.
   */
  async getErrorDetail(errorId: string): Promise<Result[]> {
    const result = await this.transport.send("rois.system.get_error_detail", {
      error_id: errorId,
    });

    const parsed = result as GetErrorDetailResponse;
    const returnCode = ReturnCodeSchema.parse(parsed.return_code);
    this.checkReturnCode(returnCode, "rois.system.get_error_detail");

    return ResultSchema.array().parse(parsed.results ?? []);
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