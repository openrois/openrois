// Re-export component modules. We explicitly list exports to avoid
// conflicts with types re-exported from $defs (e.g. ComponentStatus from common).

export {
  ROIS_COMMON_PROFILE,
  NAVIGATION_PROFILE,
  PERSON_DETECTION_PROFILE,
  REACTION_PROFILE,
  SYSTEM_INFORMATION_PROFILE,
} from "./profiles";
export {
  PersonDetectedEventSchema,
  PersonDetectionStatusResultSchema,
  type PersonDetectedEvent,
  type PersonDetectionStatusResult,
} from "./person-detection";

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
} from "./navigation";

export {
  SystemInformationRobotPositionResultSchema,
  SystemInformationEngineStatusResultSchema,
  type SystemInformationRobotPositionResult,
  type SystemInformationEngineStatusResult,
} from "./system-information";