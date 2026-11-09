// Re-export component modules. We explicitly list exports to avoid
// conflicts with types re-exported from $defs (e.g. ComponentStatus from common).

// The profile module holds only the generated constants, so a star export cannot conflict
// and a new standard component type needs no change here.
export * from "./profiles.js";

export {
  PersonDetectedEventSchema,
  PersonDetectionStatusResultSchema,
  type PersonDetectedEvent,
  type PersonDetectionStatusResult,
} from "./person-detection.js";

export {
  NavigationSetParameterSchema,
  NavigationSetParameterResultSchema,
  NavigationGetParameterResultSchema,
  NavigationStatusResultSchema,
  NavigationReachedTargetEventSchema,
  type NavigationSetParameter,
  type NavigationSetParameterResult,
  type NavigationGetParameterResult,
  type NavigationStatusResult,
  type NavigationReachedTargetEvent,
} from "./navigation.js";

export {
  SystemInformationRobotPositionResultSchema,
  SystemInformationEngineStatusResultSchema,
  type SystemInformationRobotPositionResult,
  type SystemInformationEngineStatusResult,
} from "./system-information.js";

export {
  ReactionGetParameterResultSchema,
  ReactionSetParameterSchema,
  ReactionSetParameterResultSchema,
  ReactionStatusResultSchema,
  type ReactionGetParameterResult,
  type ReactionSetParameter,
  type ReactionSetParameterResult,
  type ReactionStatusResult,
} from "./reaction.js";
